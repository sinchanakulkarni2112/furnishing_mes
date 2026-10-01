# 04 — Security Model

Security is enforced in three independent layers. A failure in one must not
expose data.

| Layer | Mechanism | Answers |
|---|---|---|
| 1. Authentication | Odoo `res.users`, password policy, session cookies | *Who are you?* |
| 2. Model access (ACL) | `res.groups` + `ir.model.access.csv` | *May you touch this model at all?* |
| 3. Record access | `ir.rule` record rules | *Which rows of it?* |
| 4. Field access | `groups=` on field definitions | *Which columns?* |

Menu visibility is a usability feature, **never** a security control. Every
restriction below is enforced at layer 2 or 3.

---

## 1. Group Hierarchy

Category: **Furnishing MES** (`module_category_furnishing_mes`).

```
base.group_portal
    └── Customer  (portal user — no internal group)

base.group_user  (internal)
    └── group_fmes_operator     "Furnishing MES / Operator"
            └── group_fmes_supervisor   "Furnishing MES / Supervisor"
                    └── group_fmes_manager  "Furnishing MES / Plant Manager"
```

Odoo `implied_ids` makes this cumulative: a Supervisor automatically holds every
Operator right, a Plant Manager every Supervisor right. Only the *increment* is
declared at each level.

| Group | XML ID | Odoo user type | Also implies |
|---|---|---|---|
| Operator | `furnishing_mes.group_fmes_operator` | Internal | `base.group_user` |
| Supervisor | `furnishing_mes.group_fmes_supervisor` | Internal | Operator, `mrp.group_mrp_user`, `maintenance.group_equipment_manager` |
| Plant Manager | `furnishing_mes.group_fmes_manager` | Internal | Supervisor, `mrp.group_mrp_manager`, `stock.group_stock_manager`, `account.group_account_invoice` (when accounting is installed) |
| Customer | `base.group_portal` | Portal | — |

### 1.1 Operator / Employee

Strictly the shop floor.

- Shop-Floor Terminal only; the backoffice MES menus are hidden and the
  underlying models are ACL-restricted regardless.
- Sees **only** work orders at work centers they are allocated to *today*
  (`fmes.operator.allocation`).
- Logs production output and work-center downtime.
- Views their own shift logs and allocations.
- Cannot see costs, prices, other departments, other operators' records,
  planning, backlog or any report.

### 1.2 Supervisor

- Shift scheduling and daily plan release for their own department(s).
- Reviews and approves production entries and downtime logs.
- Escalates downtime to maintenance requests.
- Manages operator allocation.
- Reads dashboards and reports scoped to their department(s).
- Cannot manage users, alert rules, capacity matrix, or any other department.

### 1.3 Plant Manager

Full control: MRP, maintenance, inventory, costing, master data, alert rules,
user administration within the MES, and all executive MIS dashboards. The only
group that can unlock an `approved` production entry, delete master data, or
change the capacity matrix.

### 1.4 Customer (Portal)

`/my/home` only. Sees their own orders, order progress, and their own support
tickets. Every portal query is filtered by `partner_id` on the server side — the
portal never trusts an id from the URL without an ownership check.

---

## 2. Permission Matrix

`R` read · `W` write · `C` create · `D` delete · `—` no access

| Model | Operator | Supervisor | Plant Manager | Customer |
|---|---|---|---|---|
| `fmes.shift` | R | R | RWCD | — |
| `fmes.capacity.matrix` | — | R | RWCD | — |
| `mrp.workcenter` | R | RW | RWCD | — |
| `maintenance.equipment` | R | RW | RWCD | — |
| `fmes.production.plan` | — | RWC | RWCD | — |
| `fmes.production.plan.line` | R (own WC) | RWC | RWCD | — |
| `fmes.production.entry` | RWC (own WC, own shift, draft only) | RWC | RWCD | — |
| `mrp.workcenter.productivity` | RWC (own WC, draft only) | RWC | RWCD | — |
| `mrp.workcenter.productivity.loss` | R | R | RWCD | — |
| `fmes.manpower.log` | — | RWC | RWCD | — |
| `fmes.operator.allocation` | R (own) | RWCD | RWCD | — |
| `fmes.backlog.snapshot` | — | R | R | — |
| `fmes.maintenance.schedule` | — | R | RWCD | — |
| `maintenance.request` | RC (report a breakdown) | RWC | RWCD | — |
| `fmes.alert.rule` | — | R | RWCD | — |
| `fmes.alert` | — | RW (acknowledge) | RWCD | — |
| `fmes.support.ticket` | — | RW | RWCD | RC (own) |
| `fmes.*.report` (SQL views) | — | R | R | — |
| `sale.order` | — | R | R | R (own, via portal) |
| `mrp.production` | R (own WC) | RW | RWCD | R (own, via portal) |

Backlog snapshots are cron-written and therefore never writable by a UI user —
not even the Plant Manager — which preserves the integrity of the trend series.

---

## 3. Record Rules (`ir.rule`)

### 3.1 Multi-company (applies to every model with `company_id`)

```xml
<field name="domain_force">
    [('company_id', 'in', company_ids)]
</field>
```
Global rule, all four groups.

### 3.2 Operator — own work center, own day

Operators are scoped through their allocation records, so scope follows the
roster automatically with no extra admin.

```python
# fmes.production.entry, mrp.workcenter.productivity
['&',
 ('workcenter_id', 'in',
     user.employee_id.allocation_ids
         .filtered(lambda a: a.date == fields.Date.today())
         .mapped('workcenter_id').ids),
 ('create_uid', '=', user.id)]
```

Implemented as a stored computed helper `res.users.fmes_allowed_workcenter_ids`
so the domain stays a simple `in` test and remains index-friendly.

### 3.3 Operator — draft records only (write rule)

A separate write-only rule adds `('state', '=', 'draft')`, so an operator can
correct their own entry before submission but never after a supervisor approves
it.

### 3.4 Supervisor — own departments

`res.users` gains `fmes_department_ids` (M2M `hr.department`). Empty means all
departments in the user's companies.

```python
['|', ('department_id', 'in', user.fmes_department_ids.ids),
      ('department_id', '=', False)]
```

### 3.5 Plant Manager

`[(1, '=', 1)]` within their allowed companies.

### 3.6 Portal customer

```python
# sale.order, mrp.production, fmes.support.ticket
[('partner_id', 'child_of', user.partner_id.commercial_partner_id.id)]
```

`child_of` on the commercial partner handles multi-contact customers correctly.

---

## 4. Field-Level Restrictions

| Model | Field | Visible to |
|---|---|---|
| `mrp.workcenter` | `costs_hour` | Plant Manager |
| `fmes.production.entry` | `approved_by`, `submitted_by` | Supervisor and above |
| `maintenance.request` | `fmes_cost` | Plant Manager |
| `fmes.capacity.matrix` | `efficiency_factor` | Plant Manager |
| `sale.order` (portal) | pricing fields | Handled by Odoo's native portal templates |

Declared as `groups="furnishing_mes.group_fmes_manager"` on the field itself, so
the value is stripped server-side from `read()` — not merely hidden in the view.

---

## 5. Application Hardening

### 5.1 Odoo configuration (`config/odoo.conf`)

| Setting | Development | Production | Why |
|---|---|---|---|
| `admin_passwd` | Explicit placeholder in the committed config | Strong value in a git-ignored config | Guards the database manager. Odoo 18 has **no `--admin-passwd` CLI option**, so this can only live in a config file — it cannot be injected from `.env`. The development value is stated openly rather than left at Odoo's silent default of `admin` |
| Port binding | `127.0.0.1` only | `127.0.0.1`, behind the reverse proxy | This is what makes the development master password harmless: the database manager is not reachable from the network |
| `list_db` | `True` | `False` | The first-run database wizard needs it. Production disables the database manager entirely |
| `dbfilter` | unset | `^furnishing_mes$` | Prevents cross-database probing |
| `proxy_mode` | `False` | `True` | Correct client IPs behind a reverse proxy |
| `workers` | `0` | `(2 x cores) + 1` | Single process in dev so breakpoints work |
| `max_cron_threads` | `2` | `2` or more | Four overnight crons would otherwise serialise |
| `log_level` | `info` | `warn` | |

### 5.2 Secrets

- All secrets live in `.env`, which is **git-ignored**. `.env.example` is
  committed with placeholder values only.
- `POSTGRES_PASSWORD`, `ADMIN_PASSWD` are required with no defaults — the stack
  must fail loudly rather than boot with a well-known password.
- No secret is ever written into `odoo.conf` in the repository; the entrypoint
  templates it from the environment.

### 5.3 Database

- The `db` service publishes **no host port**. It is reachable only on the
  internal `fmes-net` bridge network.
- The Odoo database user is not a PostgreSQL superuser in production.

### 5.4 Web

- Session cookies: `HttpOnly` and `Secure` (Secure requires TLS — set at the
  reverse proxy).
- CSRF protection is Odoo's default for form posts; all custom controllers use
  `type='json'` (CSRF-exempt by design and not form-replayable) or declare
  `csrf=True`.
- Portal controllers call `request.env['...'].browse(id).check_access_rights()`
  and `check_access_rule()`, or use `sudo()` **only after** an explicit ownership
  assertion. Never `sudo()` before validating.
- No raw SQL string interpolation. Parameterised queries only; the SQL-view
  models are static DDL with no user input.

### 5.5 Password and account policy

- Minimum length enforced via Odoo's `auth_password_policy` settings.
- Operators authenticate with a short PIN **only** inside the terminal, layered
  on top of a normal session — the PIN is a convenience for machine handover, not
  a replacement for login. It is stored hashed, never plaintext.
- Portal users are created by invitation (Odoo's portal wizard), never
  self-registration; `auth_signup` invite-only mode.

### 5.6 Audit trail

- `mail.thread` with `tracking=True` on all state and quantity fields records who
  changed what and when, permanently, on the record's chatter.
- Approved production entries are immutable except by Plant Manager, and every
  such unlock is tracked.
- `fmes.sync.log` will record every ERP exchange once integration is built.

---

## 6. Security Test Checklist (Phase 14 gate)

| # | Test | Expected |
|---|---|---|
| T1 | Operator opens a production entry from another work center by URL id | `AccessError` |
| T2 | Operator edits an approved entry | `AccessError` |
| T3 | Supervisor reads a plan from another department | Empty recordset |
| T4 | Portal customer requests another partner's sale order id | 404 / `AccessError` |
| T5 | Portal customer reaches any `/web` backoffice URL | Redirected to `/my` |
| T6 | Operator reads `mrp.workcenter.costs_hour` | Field absent from `read()` |
| T7 | Any user writes to `fmes.backlog.snapshot` | `AccessError` |
| T8 | Database manager at `/web/database/manager` | Blocked by `list_db = False` in production |
| T9 | Direct connection to PostgreSQL from the host | Refused, no published port |
| T10 | Company A user reads Company B records | Empty recordset |

Each is implemented as an Odoo unit test in `tests/test_security.py` and must
pass before Phase 14 is signed off.
