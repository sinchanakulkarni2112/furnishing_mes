# MEMORY.md — Project Decision Log

Running record of decisions, their reasons, and anything that will matter later.
Updated at the end of every phase, before pushing.

Newest entries at the top of each section.

---

## Project Constants

| | |
|---|---|
| Project | Furnishing MES — Manufacturing Execution System |
| Module | `furnishing_mes` |
| Platform | Odoo 18.0 **Community** Edition |
| Database | PostgreSQL 15 |
| Deployment | Docker Compose, on-prem single server |
| Repository | https://github.com/sinchanakulkarni2112/furnishing_mes |
| Branch | `main` (trunk-based) |
| Phases | 15, sequential — see `docs/06-build-plan.md` |

---

## Phase 0 — Documentation & Project Charter
*Completed 2026-09-06*

### The pivot that defined the project

The project was initially framed as React + FastAPI. It was changed, on the
mentor's requirement, to a **native Odoo 18 custom module** before any code was
written.

**Consequences that everything else follows from:**
- Odoo is both backend and frontend — Odoo ORM for logic, Odoo views + OWL 2 for UI
- Security is Odoo's own `res.groups`, ACLs, record rules and Portal
- No React, no FastAPI, no Celery, no Redis, no Nginx in the standard stack
- Exactly two containers: `web` (`odoo:18.0`) and `db` (`postgres:15`)
- `ir.cron` replaces Celery; Odoo's own web server replaces Nginx in development

This is recorded here because it is the single most important constraint in the
project, and a future session must not drift back toward the original framing.

### Decisions

**D0.1 — Odoo 18 Community capability was verified against source, not assumed.**
Blog posts and forum answers contradict each other on what Community includes.
Checked directly against `odoo/odoo@18.0` for `addons/<module>/__manifest__.py`:

| Present | Absent (Enterprise) |
|---|---|
| `mrp`, `mrp_account`, `mrp_subcontracting` | `mrp_workorder` (Shop Floor app) |
| `maintenance` | `web_gantt` (Gantt views) |
| `hr`, `resource`, `stock`, `product` | `mrp_maintenance` (workcenter↔equipment bridge) |
| `portal`, `base_automation`, `base_import` | `quality_control` |
| `sale_management`, `spreadsheet_dashboard`, `board` | |

Also confirmed in source: `mrp.workcenter` already has `oee`, `oee_target`,
`time_efficiency`, `_compute_oee()`; `maintenance.equipment` already has `mtbf`,
`mttr`, `expected_mtbf`, `latest_failure_date`, `estimated_next_failure`.

**Why it matters:** three requested capabilities (Shop Floor terminal, Gantt
scheduling, equipment bridge) must be built in-house. Discovering this in Phase 4
instead of Phase 0 would have derailed the plan.

**D0.2 — Downtime reuses `mrp.workcenter.productivity`, not a new model.**
Odoo's `_compute_oee()` derives OEE from productive versus blocked time on this
model. A parallel downtime model would leave native OEE permanently wrong.
`mrp.workcenter.productivity.loss` is already a loss-reason master with a
`loss_type` classification (availability / performance / quality / productive),
which is exactly the taxonomy the customer's downtime list implies.
*(ADR-001)*

**D0.3 — Custom OWL Shop-Floor Terminal instead of the Enterprise app.**
Not only forced by edition, but better: the stock app does not capture output,
downtime reason and manpower in one flow, which is what this plant needs. Tablet-first,
operator-scoped by the daily allocation roster, optimistic writes with retry.
*(ADR-002)*

**D0.4 — Custom scheduling board instead of Gantt or an OCA backport.**
`web_gantt` is Enterprise. An OCA substitute would mean a third-party dependency
with its own 18.0 compatibility and upgrade risk on a core screen. A purpose-built
board (machines × date-shift, coloured by load vs capacity) is similar effort,
no dependency, and answers the planner's actual question.
*(ADR-003)*

**D0.5 — Analytics read from SQL views, not Python aggregation.**
Four `_auto = False` models: `fmes.production.report`, `fmes.downtime.report`,
`fmes.utilization.report`, `fmes.maintenance.report`. The customer wants
historical trends; Python-side aggregation degrades as rows accumulate.
Materialised views are the documented escalation path if the 2 s dashboard target
is missed at 100k rows.
*(ADR-004)*

**D0.6 — Reports read only `approved` production entries.**
Draft and submitted data never reaches a report or the ERP. This is what makes
the numbers trustworthy to management, and is why the approval workflow exists.

**D0.7 — Metric definitions fixed centrally.**
`docs/11-reporting-analytics.md` §1 is authoritative. Notably: achievement % is
`SUM(actual)/SUM(planned)`, aggregated *then* divided — never the average of
per-row percentages, which would weight a 10-unit line equally with a 1,000-unit
line. Phase 12 tests that dashboard, PDF and XLSX reconcile.

**D0.8 — Four roles, mapped to Odoo natively.**
Operator, Supervisor, Plant Manager as internal user tiers with cumulative
`implied_ids`; Customer as a portal user. Operator scope is derived from
`fmes.operator.allocation` for *today*, so access follows the roster with no
extra administration.

**D0.9 — ERP 10.8 seam built dormant in Phase 1.**
`fmes.erp.sync.mixin` (external id + sync state) and `fmes.sync.log` ship in
Phase 1 and stay unused. Retrofitting external identity onto live production
records later would be a manual data-matching exercise; reserving the columns now
costs nothing.
*(ADR-006)*

**D0.10 — Mock ERP data lives in `demo/`, never `data/`.**
A production install (`--without-demo=all`) must get none of it. Real master data
arrives by import instead.

**D0.11 — 15 phases, one requirement area each where possible.**
Gives a clean traceability story and a demonstrable increment per phase.
Dependency chain: 1 → 2 → 3 → 4 → {5, 8} → 6 → 7 → 9 → 10 → 11 → 12 → 13 → 14 → 15.

**D0.12 — Commit identity is `sinchanakulkarni2112`, and authorship is human-only.**
Set **repo-locally** so this machine's other projects keep their own identity:

```
user.name  = sinchanakulkarni2112
user.email = 323928844+sinchanakulkarni2112@users.noreply.github.com
```

The `…@users.noreply.github.com` form is GitHub's privacy address for that
account (id `323928844`) — it attributes correctly on GitHub without publishing a
personal email in the history. No commit may be authored by `shreyassridhar44` /
`shreyassridhar146@gmail.com`; the two Phase 0 commits were rewritten with
`git rebase --root --exec 'git commit --amend --no-edit --reset-author'` and
force-pushed. No AI author, co-author, trailer or footer anywhere. Recorded in
`CLAUDE.md` §1 and `AGENTS.md`, verified before every push.

### Open questions for later phases

**Moved to `docs/15-open-questions-and-assumptions.md`** — 40 questions in Part A
(ordered by the phase that needs them) and 48 assumptions in Part B.

**D0.13 — No phase ever blocks on an unanswered customer question.** Where an
answer is unknown we adopt the industry-standard default, give it an assumption
ID, and implement it as a **configuration record** rather than hard-coded logic.
When the real answer arrives it is a data edit by the Plant Manager — not a code
change, not a migration, not a redeploy.

*Why:* the customer's process discovery runs in parallel with the build. This is
how manufacturing software is normally delivered under that constraint, and it
means the build proceeds at full speed while remaining honest about what is a
guess. Every guess is traceable to the record that carries it.

The highest-value answers to chase, in order: **Q5** standard output rates (the
capacity matrix — nothing about automated planning is better than this input),
**Q8** a real DAY WISE OUTPUT sample, **Q3/Q4** the real machine and department
list, **Q36–Q40** the ERP questions (longest lead time), **Q32** SMTP access.

### Delivered in Phase 0

- `docs/00` – `docs/14` plus `docs/README.md` — the full design set
- `README.md` — clone-and-run instructions
- `CLAUDE.md`, `AGENTS.md`, `MEMORY.md` — working conventions
- Odoo 18 Community capability audit

### Next

**Phase 1 — Docker Foundation & Module Skeleton.** `docker-compose.yml`,
`config/odoo.conf`, `.env.example`, `.gitignore`, the `furnishing_mes` skeleton
with its manifest and the four security groups, the dormant ERP sync mixin, the
`Makefile`, and an install smoke test.

---

## Phase 1 — Docker Foundation & Module Skeleton
*Completed 2026-09-06 · module version `18.0.1.0.0`*

### Delivered

`docker-compose.yml` (web + db, healthcheck-gated), `config/odoo.conf`,
`.env.example`, `Makefile`, and the `furnishing_mes` module skeleton: manifest
with the full verified dependency list, the three internal security groups, an
empty ACL file, the ten-section menu tree with one working leaf, the dormant ERP
sync mixin, a generated module icon, an Apps description page, and 19 tests.

### Verified, not assumed

- Module state `installed`, version `18.0.1.0.0`
- `/web/login`, `/web/health` and the module icon all return HTTP 200
- Group hierarchy read back from the database:
  Operator -> Internal User · Supervisor -> Operator + MRP User + Equipment
  Manager · Plant Manager -> Supervisor + MRP Manager + Stock Manager
- 12 menu records created
- **19 tests, 0 failed, 0 errors**
- Clean install and upgrade at `--log-level=warn`

### Decisions

**D1.1 — The master password lives in `config/odoo.conf`, not `.env`.**
Verified against `odoo/tools/config.py` on the 18.0 branch: **there is no
`--admin-passwd` command-line option**. `admin_passwd` is a config-file setting
only, so it cannot be injected from the environment the way the database
credentials can.

Rather than ship a bootstrap script (which would break "clone and run") or leave
Odoo's silent default of `admin`, the development config carries an explicit
placeholder, `fmes_dev_master_change_in_production`, and the stack **binds to
127.0.0.1 by default**. That binding is what makes the placeholder harmless: the
database manager is not reachable from the network. `ODOO_BIND=0.0.0.0` in
`.env` opens it for tablet testing on a trusted network. Production generates a
strong value into a git-ignored config (Phase 15).

**D1.2 — `list_db = True` in development.** Follows from D1.1: the first-run
database wizard needs it, and the localhost binding contains the risk. The
security doc's hardening table now separates development from production
explicitly rather than stating one value for both.

**D1.3 — Makefile odoo targets use `docker compose run --rm`, never `exec`.**
Two failures found by actually running them:
- `exec` **bypasses the image entrypoint**, so the `HOST`/`USER`/`PASSWORD`
  variables are never turned into `--db_host`/`--db_user`/`--db_password`.
  Odoo then falls back to a local unix socket that does not exist:
  `connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed`.
- `exec` shares the running server's network namespace, so a second Odoo tries
  to bind port 8069: `Address already in use`.

`run --rm` starts a throwaway container through the entrypoint and publishes no
ports, so both problems disappear — and HTTP still works inside it, which the
`HttpCase` tours in later phases will need.

**D1.4 — The `PG*` libpq variables are set on the `web` service.**
`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` are read directly by psycopg2, so
even an `exec`'d Odoo reaches the database. This keeps every credential out of
the committed `config/odoo.conf` while making both invocation styles work.

**D1.5 — One real menu leaf ships in Phase 1.** Odoo hides a parent menu with no
visible children, so a pure skeleton would have been invisible after install.
Configuration -> Machines points at `mrp.workcenter`, which Phase 2 extends
anyway.

**D1.6 — The security-baseline test is written before it can fail.**
`test_every_fmes_model_has_an_acl` is trivially true today (no models yet), but
it will fail the moment a later phase adds a model without an
`ir.model.access.csv` row. Cheaper to write now than to remember later.

**D1.7 — Dependencies verified in a test, not just in a doc.**
`test_declared_dependencies_are_installed` asserts every declared dependency
exists and is installed, so accidentally depending on an Enterprise-only module
fails the suite rather than the customer's deployment.

**D1.8 — Container, volume and network names are not pinned.**
Found by cloning the repo to a second directory and running the documented
setup: because `container_name` and the volume `name:` keys were hardcoded, the
second clone attached to the first one's PostgreSQL data directory with a
different `POSTGRES_PASSWORD` and died with
`password authentication failed for user "odoo"`.

Compose now prefixes everything with the project name, so two clones are
independent, and `COMPOSE_PROJECT_NAME` gives full isolation. Nothing was lost
by removing the pins — every command in the docs goes through
`docker compose <service>`, never `docker exec <container-name>`.

Consequence for Phase 15: the backup script must reference
`${COMPOSE_PROJECT_NAME:-furnishing-mes}_fmes-web-data`, not `fmes-web-data`.
The deployment doc has been corrected.

### Environment notes for this machine

- Docker Desktop must be running; it was not, and had to be started.
- `docker` commands fail in Git Bash with
  `docker-credential-desktop: executable file not found` — Docker Desktop's
  `resources/bin` is not on Git Bash's PATH. **Run docker from PowerShell**, or
  add that directory to PATH.

### Next

**Phase 2 — Master Data & Capacity Matrix.** `fmes.shift`, the `mrp.workcenter`
extension with the maintenance-equipment bridge, `fmes.capacity.matrix`, the
downtime loss-reason taxonomy, sequences, the mock ERP dataset, and the customer
import templates.

---

## Phase 2 — Master Data & Capacity Matrix
*Completed 2026-09-06 - module version `18.0.2.0.0`*

### Delivered

`fmes.shift`, `fmes.capacity.matrix`, the `mrp.workcenter` machine-master
extension with the maintenance-equipment bridge, the downtime loss-reason
taxonomy, five document sequences, ACLs and multi-company record rules, six
Configuration menus, and a mock plant dataset. Plus CSV import templates in
`docs/templates/` so the customer can answer Q1-Q7 with a spreadsheet.

### Verified, not assumed

- 68 tests, 0 failed, 0 errors
- Fresh-database install and in-place upgrade both clean at `--log-level=warn`
- Demo data read back from the database: 15 machines, and **all 15 bridged to
  equipment consistently in both directions**
- All ten downtime categories classified after a fresh install; "Fully
  Productive Time" correctly left uncategorised

### Decisions

**D2.1 - A missing capacity rate resolves to 0.0, not to `default_capacity`.**
The data-model doc originally said to fall back to `workcenter.default_capacity`.
That field means "pieces produced in parallel", not an hourly rate. Substituting
it would produce plans that look right and are built on an unrelated number.
Returning zero makes the gap visible to the planner. Doc corrected; the
behaviour is unit-tested precisely because it is a deliberate choice that looks
like an omission.

**D2.2 - Odoo's own loss reasons cannot be classified declaratively.**
`mrp` ships `block_reason0..7` inside `<data noupdate="1">`, which sets
`ir.model.data.noupdate` on the records themselves. Odoo then skips *any* later
`<record>` aimed at them, whatever our own data block says — silently, with no
error. Three tests failed on this before it was understood.

The fix is a `<function>` tag calling
`_fmes_apply_default_categories()`, which runs on install and on every upgrade.
It only fills in reasons that are still unclassified, so a plant that
re-classifies one keeps its change.

*Generalisable:* to modify another module's data records, use a `<function>`,
never a `<record>` — unless you have confirmed that module declares them with
`noupdate="0"`.

**D2.3 - Python `@api.constrains` does not fire for fields absent from
`create()` values.** A capacity row created with neither product nor category
skipped `_check_target_defined` entirely, because Odoo only validates
constraints whose fields appear in the write. Two fixes applied: the constraint
now also lists `workcenter_id` (always present), and a SQL `CHECK` backs it up.
Odoo inserts before validating, so the SQL constraint is what actually catches
it — and Odoo still surfaces the friendly message declared beside it.

*Generalisable:* a cross-field "at least one of" rule needs a SQL constraint,
not just `@api.constrains`.

**D2.4 - `basis_hours` on the capacity matrix.** Plants quote rates per shift or
per day as often as per hour. Normalising to hours requires knowing what the
basis represents; hard-coding 8 or 7.5 would silently distort every rate quoted
that way. The field defaults per basis (1 / 7.5 / 22.5 from A1) and is editable.

**D2.5 - The equipment bridge is two mirrored Many2ones with a context guard.**
`mrp.workcenter.equipment_id` and `maintenance.equipment.workcenter_id` are kept
in step by `create`/`write` overrides that pass `fmes_bridge_sync=True` to stop
the two models writing to each other forever. A SQL `unique(equipment_id)`
prevents one equipment record serving two machines. This is gap G3 — what Odoo
Enterprise provides through `mrp_maintenance`.

**D2.6 - Demo data is generated, not hand-written.** A build-time script emits
the four demo XML files; only the XML is committed. Keeps 40 capacity rows and
30 order pairs internally consistent, and makes regenerating with the customer's
real shape a small edit.

### Gotchas found the hard way

- **XML comments may not contain `--`.** Both `--without-demo=all` and a
  `<!-- ---------- separator ---------- -->` broke the demo files. Validate XML
  before installing; the parser error points at the comment, not the cause.
- `_read_group` in Odoo 18 returns recordset keys, so `counts.get(record, 0)`
  is the correct lookup.

### Next

**Phase 3 - Production Planning Automation.** The planning engine, plan and plan
lines, the generator wizard, and the OWL scheduling board that replaces the
Enterprise Gantt.

---

## Phase 3 — Production Planning Automation
*Completed 2026-09-06 - module version `18.0.3.0.0`*

### Delivered

`fmes.production.plan` and `.plan.line`, the `fmes.planning.engine` service, the
generator wizard with a live demand-vs-capacity preview, the OWL scheduling
board that replaces the Enterprise Gantt, plan release onto manufacturing and
work orders, and an XLSX export. Routing operations were added to the demo bills
of materials so real work orders exist.

### Verified, not assumed

- **115 tests, 0 failed, 0 errors**
- End-to-end on the demo plant: 153 demands to 246 plan lines, 96.7% utilisation
  of the slots used, and **0 capacity breaches**
- Board SCSS and OWL component confirmed to compile into `web.assets_backend`
- XLSX route tested over HTTP, including the ZIP magic bytes
- Fresh-database install clean at `--log-level=warn`

### Decisions

**D3.1 - The engine is deterministic and explainable, not optimal.**
Greedy forward scheduling, earliest deadline first, with every tie broken on a
stated key so the result never depends on database ids. A planner coming off
spreadsheets needs to understand why a line landed where it did; an optimiser
that saves an hour at the cost of explainability is a poor trade here. Ordering
is unit-tested by generating twice and comparing signatures.

**D3.2 - Demand the engine cannot place is reported, never dropped.**
`plan.unscheduled_demand_note` names the order, the product, the quantity and
the reason. Silently shrinking demand to fit capacity is the single most
damaging thing a scheduler can do.

**D3.3 - Quantities are rounded so that hours always equal qty / rate +
changeover.** Found by a failing test: the engine sized hours from an unrounded
quantity while Odoo stored the quantity rounded, so the two disagreed in the
sixth decimal. A first clamp fix held the capacity line but broke the identity.
The right answer is to round the quantity *first* - down when filling a slot so
the hours still fit, exactly when the slot can absorb the remainder so no crumb
is left behind and falsely reported as unscheduled.

**D3.4 - Shift slots resolve in the company's timezone, not the user's.**
The first run scheduled a 06:00 shift to 04:00 UTC because the demo admin sits
in Europe/Brussels. A shift belongs to the plant: the same shift must resolve to
the same instant whoever generates the plan, or a manager working remotely
schedules the shop floor into different hours than the supervisor standing in
it. Unit-tested with two users in different timezones.

**D3.5 - The manpower factor is a real hook returning 1.0 until Phase 8.**
It is applied in `_slot_capacity_hours` like any other factor, but there is no
roster to read yet. Building a half-real constraint against a model that does
not exist would be worse than an honest placeholder. Phase 8 replaces one method
body; nothing else in the engine changes. The test asserts the documented
behaviour so the placeholder cannot be forgotten.

**D3.6 - Availability derates from real downtime history.** Planning every
machine at 100% availability is the commonest reason plans cannot be met, so the
engine reads the last 90 days of unplanned stoppages, excluding planned ones. It
returns 1.0 while there is no history, which is the case until Phase 5, and
never derates below 0.5 - a machine that broke down constantly last quarter is a
maintenance problem, not a reason to plan it at near-zero.

**D3.7 - Moving a line on the board re-sizes it against the target machine.**
The same quantity takes a different time on a different machine, and the setup
cost belongs to the machine being moved *to*. The server refuses a move that
would overload the target and says by how much; a board that lets a planner
build an impossible plan is worse than no board.

**D3.8 - Routing operations added to the demo BOMs.** Without them an order has
no work orders, so there is no machine-wise schedule to build and nothing for
the Phase 4 terminal to show. `mrp.production.workorder_ids` is a stored
compute, so Odoo creates them automatically on record creation - no confirm step
needed in demo data.

### Gotchas found the hard way

- **A test fixture can quietly invalidate its own premise.** The "unrated"
  product sat under a category whose *parent* carried a rate, so it resolved
  fine and the test asserting it could not be planned failed. It now has its own
  category tree.
- **`docker compose exec` cannot pipe a script from PowerShell** without a BOM
  being prepended, which Python rejects as `U+FEFF`. Pipe from Bash instead.

### Next

**Phase 4 - Daily Tracking & Shop-Floor Terminal.** `fmes.production.entry`, the
OWL tablet terminal, the supervisor approval queue, planned-versus-actual views,
and the DAY WISE OUTPUT importer.

---

## Phase 4 — Daily Tracking & Shop-Floor Terminal
*Completed 2026-09-06/07 - module version `18.0.4.0.0`*

### Delivered

`fmes.production.entry` (draft -> submitted -> approved), `fmes.import.batch`,
the operator machine-scoping fields on `res.users`, live machine status on
`mrp.workcenter`, the OWL shop-floor terminal with its `/fmes/terminal/*`
JSON-RPC endpoints, the DAY WISE OUTPUT importer wizard (configurable column
mapping, guessed from headers), the approval queue, planned-vs-actual views,
and the daily entry-generation cron.

### Verified, not assumed

- **169 tests, 0 failed, 0 errors**
- Fresh-database install clean at `--log-level=warn`
- End-to-end on the demo plant: plan released (246 lines) -> 82 entries
  generated from it (second generation run produced 0 - confirmed idempotent)
  -> output recorded -> submitted and approved -> 61 plan lines `done`, 21
  `partial` -> the 203.77-unit shortfall carried into the next plan -> a write
  to an approved entry's `actual_qty` raised `AccessError`
- Backend CSS bundle compiles with both `fmes-board` and `fmes-terminal` rules
  present (see D4.5 below - it did NOT compile on the first attempt)

### Decisions

**D4.1 - Only `state='approved'` entries may ever feed a report or KPI.**
Everything downstream (Phase 6 onward) must filter on this. Restated here
because it is the single rule Requirement 3.4 and the "no restating history"
guarantee both depend on, and getting it wrong once poisons every later phase
silently.

**D4.2 - The state lock closes the direct-write hole, not just the UI.**
`write()` blocks `state='approved'` unless the caller is a supervisor/manager
or `self.env.su`. Discovered by testing: a plain `search().write({'state':
'approved'})` bypasses `action_approve()` and every check inside it, and Odoo's
record rules do not catch this on their own -- they evaluate against the record
as it currently is, not as the write would make it. The superuser exemption
(`self.env.su`) is required too, or crons and data loads (including this
project's own tests) fail approving anything, which is a bug, not security.

**D4.3 - Approval writes actual output back onto the plan line
(`_sync_plan_line`), closing the loop opened in Phase 3.** Only *approved*
entries move `qty_done`; submitted-but-unapproved output does not touch the
plan. Reopening an approved entry (Plant Manager only) rolls the plan line back
to `pending`/`partial`, so the state machines for entry and plan line can never
drift out of step with each other. This is what makes the shortfall carry
forward automatically in Phase 3's engine without either model needing to know
about the other's internals.

**D4.4 - Every `/fmes/terminal/*` route re-derives the caller's rights from the
server, never trusts what the client sent.** The terminal runs on a shared
tablet -- the least trustworthy client in the building. `_check_workcenter`
re-validates the machine id against `_allowed_workcenter_ids` on every call;
`record()` accepts only an explicit whitelist of fields (`actual_qty`,
`rejected_qty`, `run_hours`, `downtime_hours`, `actual_manpower`, `note`) and
silently drops anything else in the payload, so a crafted request setting
`state` or `planned_qty` has no effect. Unit-tested by sending exactly that
payload and asserting nothing outside the whitelist moved.

**D4.5 - `sudo()` only after the machine is already authorised, and only for
what an operator has no rights on.** Live machine status reads
`mrp.workorder`/`maintenance.request`, which operators cannot see directly.
`_check_workcenter()` runs first and raises if the machine is not theirs;
`sudo()` is called only on a machine that has already passed that gate. This is
the "assert ownership before `sudo()`" rule from the security doc, applied for
real rather than as a principle.

**D4.6 - `min(420px, 100%)` in SCSS broke the entire backend asset bundle, not
just the terminal.** Sass claims `min()` as its own function and refuses to mix
`px` with `%`, so the whole `web.assets_backend` compile failed -- which would
have taken Odoo's own UI styling down with it, not merely left the terminal
unstyled. Found only by forcing a bundle rebuild and reading the compile
traceback; the earlier "does `fmes-terminal` appear in the CSS" check had
silently passed on a stale cached bundle. Fixed with explicit `width: 420px;
max-width: 100%;`. `minmax()` inside `repeat()` is unaffected -- Sass does not
intercept CSS Grid's own `minmax`.

*Generalisable:* never trust "is my string present in the compiled bundle" as a
green signal without first clearing cached `ir.attachment` asset records -- a
compile failure can leave the previous good bundle serving silently. Also:
CSS's own `min()`/`max()`/`clamp()` are unsafe to write literally in an Odoo
SCSS file: use two declarations (`width` + `max-width`) instead.

**D4.7 - The DAY WISE OUTPUT importer is built to a configurable, guessed
column mapping -- never a fixed layout.** The real file (question Q8) is still
unseen. Header titles are matched against keyword hints (`_guess_mapping`) to
pre-fill the mapping form, which the user can still override before
previewing. When the real file arrives, onboarding it is a mapping choice, not
a rework. Every import is a reversible `fmes.import.batch`; reverting is
refused if any of its entries were approved, so a bad import cannot be used to
quietly erase signed-off history via the back door.

**D4.8 - Operator machine scoping uses a real, permanent assignment
(`res.users.fmes_workcenter_ids` / `fmes_department_ids`), not a placeholder.**
`fmes.operator.allocation` (the *daily* roster) arrives in Phase 8, but a
permanent "this person normally runs these machines" assignment and a "today
this person is on this machine" allocation are genuinely different pieces of
information, and both are useful once the roster exists. An operator with no
assignment is not locked out (the terminal would be useless on day one) but is
scoped down to seeing only entries they created themselves -- never the whole
plant by default.

**D4.9 (assumption revision, A16) - No per-operator PIN; individual Odoo
logins instead.** The Phase 0 assumption proposed a shared machine session with
a PIN. Building it in Phase 4 without deciding this would mean guessing a whole
second authentication mechanism. Individual logins are simpler, give
`create_uid`/`submitted_by` real meaning for the audit trail, and Odoo's own
login is fast enough on a saved/kiosk browser that the "40 logins a shift"
friction the PIN was meant to avoid does not really apply. Recorded in
`docs/15-open-questions-and-assumptions.md`; a PIN can still be layered on top
later without changing the terminal if the plant insists on shared-tablet
handover (question Q12 downgraded from Medium to Low impact).

### Next

**Phase 5 - Downtime Management.** Extends `mrp.workcenter.productivity`
(already scaffolded in Phase 2's `fmes_category` field) with a shift/entry
link, an approval workflow mirroring the production entry's, and replaces
`fmes.production.entry.downtime_hours` -- currently a single typed number --
with the sum of coded downtime events, so every lost hour finally carries a
reason. Auto-escalation to `maintenance.request` for reasons flagged
`fmes_requires_maintenance` (already seeded in Phase 2) is the other half of
this phase.

---

## Phase 5 — Downtime Management
*Completed 2026-09-07 - module version `18.0.5.0.0`*

### Delivered

`mrp.workcenter.productivity` extended with the shift/entry link, plant
category, remarks, reporter, a draft/approved/rejected workflow and the
maintenance-escalation link; the reason-picker-and-running-timer downtime flow
in the shop-floor terminal, replacing Phase 4's plain typed-hours field; the
supervisor downtime approval queue; auto-escalation to `maintenance.request`
at creation time (not approval time - a broken machine needs attention now);
`fmes.downtime.report`, the SQL view backing loss analysis; and the seeded
default maintenance team that a production install would otherwise lack.

### Verified, not assumed

- **216 tests, 0 failed, 0 errors**
- Clean install on three separate fresh databases: with demo data, and
  explicitly `--without-demo=all` (the real production path) - both zero
  warnings
- End-to-end on the demo plant: plan -> entries -> six coded downtime events
  (one auto-escalating) -> `downtime_hours` rolled up automatically -> entries
  and downtime both approved -> an approved event correctly refused further
  edits -> `fmes.downtime.report` showed 3.25 hours across the events after an
  explicit flush -> a rejected event, edited by the operator who logged it,
  correctly returned to draft
- Escalation confirmed working against a true zero-demo-data database, using
  the seeded "Machine Maintenance" team preferentially over an unrelated
  auto-created one

### Decisions

**D5.1 - Every `mrp.workcenter` silently inherited the company's Mon-Fri
business-hours calendar, which zeroed downtime duration outside those hours.**
The single most consequential bug this phase found. Odoo's native
`mrp.workcenter.productivity.duration` compute calls
`loss_id._convert_to_duration()`, which — for any non-productive/performance
loss type on a work center that HAS a `resource_calendar_id` — computes
duration from that calendar's scheduled working hours, not wall-clock elapsed
time. Every machine gets a calendar by default via `resource.mixin`. A plant
running three shifts is down for stretches of every 24 hours a Mon-Fri 8-5
calendar knows nothing about: a night-shift stoppage computed to exactly 0.0
minutes. Found by a duration test returning 0.0 for a real 45-minute
stoppage — not by inspection; nothing before Phase 5 ever read `duration`.

Fixed by defaulting `mrp.workcenter.resource_calendar_id` to empty in our own
extension. This module's capacity and availability model is `fmes.shift`
(Phase 3, D3.4) — never Odoo's resource calendar — so the field should never
have carried a value here at all. Affects every machine created since
Phase 2; a genuinely fresh install is what surfaces the fix, not an upgrade of
a live database (the ORM field default only applies at record creation).

*Generalisable:* a field carrying a default inherited from a mixin
(`resource.mixin`, here) can silently change the behaviour of a DIFFERENT
native computation (`_convert_to_duration`) that reads it, in a way that has
nothing to do with why the mixin was inherited in the first place. Check what
else a native field feeds before assuming an unused-looking default is inert.

**D5.2 - Field-level `groups=` blocks a write even to CLEAR a restricted field
to False.** The auto-revert-to-draft path (editing a rejected event returns it
to draft, D5.-adjacent design decision below) included the supervisor-only
`fmes_approved_by`/`fmes_approved_on` in the SAME vals dict as the operator's
own edit, just to null them out — and Odoo refuses the whole write regardless
of the value, because `groups=` is a field-existence check, not a value check.
Fixed by moving the stamp-or-clear of those two fields into a separate,
narrow `sudo()` write, decoupled entirely from the caller's own vals.

*Generalisable:* never let a supervisor-only field ride along in vals a
non-supervisor's own write constructs, even to null it — sudo() a dedicated
follow-up write for administrative metadata instead.

**D5.3 - Supervisors and managers were caught by the OPERATOR's own
restrictive record rules, because the role hierarchy is cumulative.** Phase
1's `implied_ids` design means a Supervisor IS, transitively, an Operator too
— real group membership, not just a permission superset. Odoo evaluates a
non-global `ir.rule` against every group a user belongs to, INCLUDING implied
ones. With no OTHER non-global rule on `mrp.workcenter.productivity` for
`group_fmes_supervisor` to OR against, the operator's restrictive domain
silently applied to supervisors and managers as well — surfaced as a Plant
Manager unable to even READ their own record while trying to reopen it.
`mrp.group_mrp_user`'s native ACL grants the base RWCD permission; it does
nothing to exempt anyone from an `ir.rule` domain, because ACLs and record
rules are different layers entirely.

Fixed with an explicit, unrestricted `[(1,'=',1)]` rule for
`group_fmes_supervisor` — the EXACT pattern Phase 4 already used for
`fmes.production.entry` (`fmes_entry_supervisor_rule`), just missed here on
the wrong assumption that the native ACL alone would be enough this time.

*Generalisable, and now a hard project rule:* **any model that gets an
operator-scoped RESTRICTIVE `ir.rule` must ALSO get an explicit unrestricted
rule for `group_fmes_supervisor` in the SAME commit**, precisely because of
the cumulative hierarchy. Audited the rest of the record rules file while
fixing this: `fmes.production.plan`/`.plan.line`/`fmes.capacity.matrix`/
`fmes.shift` all use ACL-level restriction (`perm_write=0` for operator), not
`ir.rule`-level, so they were never exposed to this trap. Only
`fmes.production.entry` (Phase 4, already correct) and
`mrp.workcenter.productivity` (Phase 5, now fixed) carry operator-restrictive
record rules.

**D5.4 - `@api.constrains` on a computed field is not reliable enough for a
caller to catch, once `mail.thread` tracking is in the mix.** Both
downtime-categorisation rules read `fmes_category`, a stored related field.
Discovered the hard way: a `/fmes/terminal/downtime/start` request correctly
caught its own `ValidationError` and returned `{'ok': False, 'error': ...}` —
confirmed by instrumented logging showing "CAUGHT" — and the test STILL saw an
uncaught exception. Fetching the raw HTTP response body (bypassing the test
helper's own interpretation) showed why: Odoo's HTTP layer flushes the
environment AFTER the controller returns, inside its own
`_transactioning`/`retrying` wrapper, entirely outside any try/except the
controller can write — and THAT flush re-triggers `mail.thread`'s own
`_compute_field_value` -> `_validate_fields()` for the tracked, computed
field, raising the SAME constraint a second time, this time with nothing
catching it. An explicit `event.flush_recordset()` inside the controller's
own try block was NOT sufficient on its own to fully drain whatever
mail.thread schedules — only `_check_one_open_event_per_machine`, which
depends on plain, uncomputed fields, fired reliably and synchronously the
whole time.

Fixed at the right layer — the MODEL, not the controller — by validating both
rules early and synchronously in `create()`/`write()`, reading the loss
reason's category DIRECTLY (`self.env['mrp.workcenter.productivity.loss'].
browse(loss_id).fmes_category`) rather than through the computed
`fmes_category` field. This needs no flush and cannot be deferred: it either
raises right there, in the caller's own call stack, or it does not raise at
all. The `@api.constrains` versions stay as a documented backstop.

*Generalisable, and the most important lesson of this phase:* **never rely on
`@api.constrains` alone for a rule a calling layer (especially a JSON-RPC
controller) must be able to catch reliably, once the constraint depends on a
COMPUTED field on a model with mail.thread tracking enabled.** Validate early,
in plain Python, in create()/write() itself, reading the underlying data
directly rather than through the compute. This generalises to ANY future
model built the same way (extend a core model, add mail.thread, add a
constrains on a related+stored field) — audit for this pattern before shipping
a controller that depends on catching it.

**D5.5 - `action_reject()`'s chatter note must be best-effort, never able to
undo an otherwise-successful rejection.** Found running the end-to-end script
with a demo user that had no email configured: `message_post()` requires a
sender email, and its `UserError` propagated out of `action_reject()` even
though the STATE CHANGE (the actual rejection) had already been written.
Wrapped in a narrow `try/except UserError: pass` — the note is an audit-trail
nicety, not something that should be able to block the action it is
documenting.

**D5.6 - Downtime correctly reduces OEE once productive time is logged, but
nothing in the system logs productive time yet — recorded as a Phase 6
prerequisite, not a Phase 5 gap.** Odoo's native OEE is
`productive_time / (productive_time + blocked_time)`, both sides read from
`mrp.workcenter.productivity`. Phase 5 (correctly, per its own scope) only
ever writes the LOSS side; `fmes.production.entry.run_hours` is a plain number
that has never been mirrored into a `loss_type='productive'` productivity
record. Consequence, confirmed on the demo plant: every machine's native OEE
currently reads 0.0%, however accurately its downtime is coded, because the
denominator's productive component is always zero. The Phase 5
"OEE consistency" test is deliberately narrower than this and still correct:
it proves our downtime extension does not BREAK native OEE once productive
time exists (by logging both sides itself, inside the test) — it never
claimed the system produces meaningful OEE unassisted before Phase 6 wires up
the productive side. Added explicitly to Phase 6's deliverable list in the
build plan so it is not rediscovered as a surprise.

### Gotchas found the hard way

- **A duration/timing bug can hide behind a passing test suite until the
  first test that actually reads the affected field.** `resource_calendar_id`
  had been silently wrong since Phase 2; nothing broke until Phase 5 read
  `duration` for the first time.
- **"Is my class name in the compiled CSS" is not a green signal on its own**
  (restated from Phase 4, D4.6) — and neither, it turns out, is "did my
  try/except log that it caught the exception": check the actual wire
  response when a test's OWN interpretation of a result is in question, not
  just whether your code path executed.
- **A quick shell reproduction that "just works" does not rule out a bug that
  only manifests through the real HTTP dispatch path.** The difference here
  was Odoo's own post-dispatch flush, which a shell session never triggers
  the same way. When a shell test and an HTTP test disagree on IDENTICAL
  application code, suspect the FRAMEWORK layer around the code, not the code
  itself, before adding more workarounds to the code.
- **`env.cr.flush()` before querying a `_auto=False` SQL-view report model**
  is needed whenever the query runs in the SAME transaction as an unflushed
  write — a raw SQL view sees only what has actually reached the table. Real
  HTTP usage never hits this (Odoo flushes and commits between every
  request), but a one-session debugging/demo script will, and a "0 rows"
  result from a report immediately after writing the data it should contain
  is the tell.

### Next

Phase 7 - Maintenance Management.

---

## Phase 6 — Machine Utilisation & OEE
*Completed 2026-09-07 - module version `18.0.6.0.0`*

### Delivered

`fmes.utilization.report`, the SQL view backing utilisation and OEE analysis
(date x shift x machine grain, FULL OUTER JOIN of approved production and
approved downtime); `fmes.utilization.service` — rolling 30-day utilisation
per machine, under-utilised detection (worst-first), bottleneck ranking
(highest-utilisation-first) and a deterministic `_suggest_bottlenecks()`
recompute; `mrp.workcenter.fmes_utilization_pct` / `fmes_is_under_utilized`
computed fields feeding the machine kanban card and list column; the
"Suggest Bottlenecks" bulk server action; and, per D5.6,
`_fmes_sync_productive_time()` — mirroring an approved entry's `run_hours`
into a `loss_type='productive'` `mrp.workcenter.productivity` record, which is
what finally lets native `mrp.workcenter.oee` read a non-zero value.

### Verified, not assumed

- **235 tests, 0 failed, 0 errors**
- Clean install on the dev database and a fresh `--without-demo=all`
  database, both zero warnings; module version confirmed `18.0.6.0.0` in
  `ir_module_module` on both
- End-to-end on the demo plant: a demo machine's native `oee` read `0.0`
  before this phase (D5.6's gap) - approving a production entry with
  `run_hours=3.0` against it mirrored the productive-time log and `oee`
  immediately read `100.0`; `fmes_utilization_pct` read `40.0` (3 of 7.5 net
  shift hours). `_suggest_bottlenecks()` run against the demo plant correctly
  CLEARED three machines that demo data had pre-flagged `fmes_is_bottleneck`
  by hand but whose current rolling utilisation no longer clears the 90%
  threshold - proof the recompute is a live function of current data, not a
  label that just gets carried forward.

### Decisions

**D6.1 - A raw SQL view (`_auto = False`) does not get the ORM's usual
auto-flush before `search()`, and a test can hit this even without a
hand-written debugging script.** MEMORY.md already carried this exact gotcha
from Phase 5's `fmes.downtime.report` — and it still cost a real, reproduced
test failure here: `TestUtilizationReportAccess.test_supervisor_can_read_the
_utilization_report` intermittently found zero rows, searching the view as a
different user immediately after approving the entry that should populate it.
A regular model's `search()` flushes the stored fields it depends on
automatically; `fmes.utilization.report`'s hand-written SQL has no such
dependency graph for the ORM to flush against, so `_fmes_sync_productive_time
()`'s own write (and the entry's own computed fields) could still be sitting
in the ORM cache, never having reached `fmes_production_entry` /
`mrp_workcenter_productivity` in Postgres, when the view's query ran.
Reproduced deterministically: running the single test method alone passed
(its own preceding code happened to flush incidentally); running it as part
of its class, after a sibling test, failed the same way every time — not
flaky, just genuinely missing a flush. Fixed by calling `self.env.flush_all()`
explicitly before every test in this phase that reads the view, including a
class-wide `setUp()` for the tests that read it indirectly through
`fmes.utilization.service`.

*Generalisable, restated because it was already written down once and still
got missed:* **any test that writes through the ORM and then reads a
`_auto=False` SQL view in the same transaction must call `self.env.flush_all
()` between the two, unconditionally** - a helper that already does this
(like this phase's own `_report_row()`) is not a substitute for auditing
every OTHER place in the same test file that touches the view a different
way (raw `search()`, or indirectly through a service method's `_read_group`).

**D6.2 - The view's own docstring claimed something the SQL didn't actually
do.** It said a downtime event logged with no linked production entry would
still surface as its own row, via the `FULL OUTER JOIN`. In fact
`mrp.workcenter.productivity.fmes_shift_id` is a *related* field off
`fmes_entry_id` (Phase 5) - an entry-less event has no shift to place it in,
and the view's SQL filters `p.fmes_shift_id IS NOT NULL` precisely because the
report's grain is date x SHIFT x machine. Caught on re-reading the docstring
against the SQL rather than by a failing test (nothing exercised the claim).
Corrected the comment to say what actually happens - that event still counts
toward the machine's own MTBF/MTTR once Phase 7 adds it - rather than leave a
documented behaviour the code does not provide.

*Generalisable:* a comment describing what a JOIN is "for" is a claim about
behaviour, not just intent - check it against the actual WHERE clause before
trusting it, especially on a view with a fixed grain that a general-purpose
join strategy does not automatically respect.

### Next

Phase 9 - Backlog & Carry-Forward.

---

## Phase 8 — Manpower & Resource Management
*Completed 2026-09-07 - module version `18.0.8.0.0`*

### Delivered

`fmes.manpower.log` (standard vs actual headcount, absence, overtime,
shortage/shortage_pct/utilization_pct — the same sum-then-divide standard-
vs-actual maths as everywhere else, D0.7) and `fmes.operator.allocation`
(the daily roster, unique per employee/shift/day, with a "Copy to Next Week"
bulk action); `res.users.fmes_allowed_workcenter_ids` now reads today's
roster FIRST, falling back to the permanent assignment and then the
department-wide default in that order; `fmes.planning.engine.
_get_manpower_factor` replaced its Phase-3 placeholder with a real
roster-vs-standard derating, floored the same way `_get_availability_factor`
already is; and `fmes.manpower.impact.report`, the date x shift x department
view putting shortage % and achievement % side by side.

### Verified, not assumed

- **297 tests, 0 failed, 0 errors**
- Clean install on the dev database and a fresh `--without-demo=all`
  database, both zero warnings; module version confirmed `18.0.8.0.0` in
  `ir_module_module` on both
- End-to-end on the demo plant: Panel Saw 01 fully staffed today (2 of its
  standard 2) read a manpower factor of `1.0`; rostering only one of the two
  for tomorrow dropped it to `0.5` — and generating tomorrow's plan actually
  used it, landing the saw's line at `3.75` planned hours, exactly half its
  normal 7.5-hour capacity, not just an isolated factor calculation. An
  operator linked to that roster read zero allowed machines before being
  rostered and exactly the rostered machine once added.

### Decisions

**D8.1 - Assumption `A49` had already been used once, and Phase 6 silently
duplicated it.** `A49` originally named the exact placeholder this phase
resolves (`_get_manpower_factor` returning a flat `1.0` "until Phase 8").
Phase 6 assigned `A49` a SECOND time, to the unrelated bottleneck-suggestion
threshold, without the collision being noticed — the check at the time was a
`grep` for the ID pattern piped through `sort -u`, which DOES dedupe
identical strings but does not flag two DIFFERENT rows that happen to share
an ID; the two entries sat far enough apart in an eighty-plus-row document
that a visual scan of the sorted list missed it too. Found only because this
phase needed to read the ORIGINAL `A49` and discovered a second row under
the same heading. Fixed by renumbering the Phase 6 entry to `A52` (the next
free id) and leaving the original in place, since resolving it is literally
what this phase does.

*Generalisable:* **grep the exact assumption ID string before assigning a
new one** (`grep -n 'A49' docs/15-...md`), not just a sorted listing of all
IDs — a sorted list surfaces gaps, not collisions, and a collision is the
more dangerous of the two (two DIFFERENT things silently sharing one
citation, rather than a missing one).

**D8.2 - Department-scoped supervisor rules, promised since Phase 1, needed
a genuine Python conditional in `domain_force`, not a domain clause.**
`res.users.fmes_department_ids`'s own help text has always said "leave empty
for all" — so the rule cannot be a static domain; it has to read as "if this
user's own department list is empty, see everything, else restrict to it."
Written as `[(...)] if user.fmes_department_ids else [(1,'=',1)]` — a full
Python conditional EXPRESSION evaluating to one of two domain lists, which
`ir.rule.domain_force`'s own `safe_eval` supports and is a more readable
answer than trying to fold the same logic into a single OR'd domain. The
same D5.3 cumulative-hierarchy pattern applies one level up here too: without
an explicit unrestricted rule for `group_fmes_manager` on both new models, a
Plant Manager with no personal `fmes_department_ids` set would be caught by
the supervisor's own department-scoped rule, exactly the way an unscoped
Supervisor rule once caught Operators. Scoped to this phase's own two new
models only — retrofitting the same pattern onto `fmes.production.entry`,
`mrp.workcenter.productivity` and the plan/plan-line pair is real, useful
work, but a separate exercise, not something to fold into this commit
unannounced.

**D8.3 - Two Odoo-18-specific view/field validation errors, both caught by
the install itself.** `tracking=True` is not a valid parameter on a
`Selection` field on a model that does not inherit `mail.thread` — Odoo
warns rather than fails, but it is dead configuration, so it was removed
rather than left as noise (`fmes.operator.allocation` has no chatter).
`quick_add` is not a valid attribute on `<calendar>` in Odoo 18's view
schema — this one DOES fail the install (a RelaxNG validation error), caught
immediately on the first `-u` run.

---

## Phase 7 — Maintenance Management
*Completed 2026-09-07 - module version `18.0.7.0.0`*

### Delivered

`fmes.maintenance.schedule` (time-based or usage-based preventive templates,
never appearing on anyone's work queue directly) plus
`fmes.maintenance.checklist.line`; the `fmes_generate_preventive_requests`
cron, which raises a real `maintenance.request` `lead_time_days` ahead of
`next_due_date` and refuses to raise a second one while the first is still
open; usage-based triggering off accumulated approved productive hours
(`_check_usage_triggers`, assumption A51); the `maintenance.request`
extension (work center, origin schedule, a frozen `fmes_due_date` snapshot
for PM-compliance, the downtime link, cost, a snapshotted checklist result);
`maintenance.equipment.fmes_health_score` (assumption A50); and
`fmes.maintenance.report`, the month x equipment SQL view, with `mtbf`/`mttr`
layered on top as ordinary computes reading the native equipment fields
directly rather than reimplementing them.

### Verified, not assumed

- **268 tests, 0 failed, 0 errors**
- Clean install on the dev database and a fresh `--without-demo=all`
  database, both zero warnings; module version confirmed `18.0.7.0.0` in
  `ir_module_module` on both
- End-to-end on the demo plant: backdating a schedule's `last_done_date` put
  it inside its own lead-time window -> the cron raised exactly one
  preventive request -> a second cron run raised nothing further -> marking
  it done moved `last_done_date` forward and recomputed `next_due_date` a
  month out -> a breakdown logged against the same machine produced a
  corrective request carrying its work center and a live downtime figure
  (0.0h running, ~0.22h once stopped) -> the equipment's health score read
  92 (100 minus the 8-point penalty for that one recent breakdown) -> the
  KPI report showed 6 equipment/month rows, `mtbf`/`mttr` read straight off
  the native equipment fields.

### Decisions

**D7.1 - Native `maintenance.equipment` carries its own restrictive record
rule that our own ACL grant does not override.**
`maintenance/security/maintenance.xml`'s `equipment_rule_user` limits anyone
WITHOUT `maintenance.group_equipment_manager` to equipment they personally
follow (a mail.thread follower, via `message_partner_ids`) — supervisors and
managers are exempt because `group_fmes_supervisor` implies
`group_equipment_manager` (Phase 1), but operators are not. Our own
`ir.model.access.csv` grants operators plain read on `maintenance.equipment`,
which made it look safe to read `equipment.mtbf` / `.expected_mtbf` directly
in the health-score compute — a test proving an operator could read the
score on a machine they do not follow failed with a genuine `AccessError`,
the ACL and the record rule being two different, independently-enforced
layers (the same class of gap D5.3 found on our OWN rules, this time on a
NATIVE one). Fixed by reading `mtbf`, `expected_mtbf`, `fmes_schedule_ids`
and `maintenance_ids` through `equipment.sudo()` inside the compute — the
score is a read-only 0-100 summary, not the underlying rows, so it should
not depend on who happens to follow this specific equipment record.

Left alone, out of this phase's scope: `mrp.workcenter._compute_fmes_current
_state` (Phase 2/4) searches `maintenance.request` the same non-sudo way to
decide whether a machine shows as "under maintenance," and is likely exposed
to the identical gap for an operator with no personal history on that
request — worth revisiting whenever operator-facing machine status is
touched again (Phase 11's alert work is the natural point).

**D7.2 - Native `maintenance.request.write()` re-stamps `close_date` to the
real "today" whenever `stage_id` is in the same vals dict, silently
overriding any explicit `close_date` passed alongside it.** Found by a
PM-compliance test that backdated a request's close date to prove an
on-time closure — it passed on the first attempt, but for the wrong reason:
the real test-run date happened to still read as "late" against the fixed
due date used, coincidentally matching what the test expected. Re-ordering
the assertion (proving the ON-TIME case, where the coincidence broke) is
what surfaced it. Fixed with a second, separate `write({'close_date': ...})`
call after the stage-changing one — the same "two writes, deliberately"
shape Phase 5 already uses for `fmes_approved_by`/`_on` (D5.2).

*Generalisable:* when native code re-derives a field as a SIDE EFFECT of a
write (not just defends it), passing your own value for that field in the
SAME vals dict is not reliable — a separate follow-up write is the only way
to know which one wins.

**D7.3 - The month x equipment grain needed its own frozen due-date, not
just the schedule's live `next_due_date`.** `fmes.maintenance.schedule.
next_due_date` moves forward the moment a cycle completes, so by the time
anyone looks BACK at a historical request to judge "was it closed on time,"
the schedule's own field no longer reflects what was due for THAT specific
visit. Added `maintenance.request.fmes_due_date` — not in the original
Phase 0 field list, but the same reasoning Phase 4/5 apply to an approved
entry's own frozen figures — a snapshot taken once, at generation, never
touched again. `fmes.maintenance.report` also needed its own `has_pm_due`
boolean, the same null-handling pattern `has_target` established in Phase 4:
a month with no PM due for a machine reads as "—", not a misleading 0%.

---

## Conventions Established

| Convention | Where documented |
|---|---|
| Model naming `fmes.<entity>`; core-model fields `fmes_` prefixed | `CLAUDE.md` §4 |
| Every model ships with ACLs and record rules in the same commit | `CLAUDE.md` §4 |
| Business logic in models and `services/`, never views or controllers | `docs/02-architecture.md` A3 |
| Extend Odoo rather than build parallel models | `docs/02-architecture.md` A1 |
| Conventional Commits, human authorship only | `docs/12-git-workflow.md` |
| Phase gate: install + tests + docs + commit + push | `docs/06-build-plan.md` |

---

## Gotchas Worth Remembering

- **A field's default, inherited from a mixin, can silently change a
  DIFFERENT native computation that happens to read it.** `mrp.workcenter`'s
  default `resource_calendar_id` (from `resource.mixin`) made every downtime
  duration outside Mon-Fri 8-5 compute to zero, via a totally different code
  path (`mrp.workcenter.productivity._compute_duration`). Check what else a
  native field feeds before assuming an unused-looking default is inert.
- **Field-level `groups=` blocks a write even to clear the field to `False`.**
  Stamp or clear a restricted field in its own `sudo()` write, never mixed
  into a non-privileged caller's own vals.
- **Any model with an operator-scoped RESTRICTIVE `ir.rule` needs an explicit
  unrestricted rule for `group_fmes_supervisor` too, in the same commit.**
  The role hierarchy is cumulative (`implied_ids`), so a Supervisor and
  Manager ARE, transitively, Operators — Odoo evaluates a non-global
  `ir.rule` against every group a user belongs to, including implied ones,
  and a native ACL grants the base permission but does not exempt anyone
  from an `ir.rule` domain. Audit every model that adds an operator record
  rule for this.
- **`@api.constrains` on a computed field is not reliable enough for a
  caller to catch, once `mail.thread` tracking is involved.** Odoo can defer
  that field's recompute-and-validate cycle past `create()`/`write()`
  returning, to the framework's OWN next flush — for a JSON-RPC controller,
  that is the HTTP layer's post-dispatch `env.cr.flush()`, outside any
  try/except the controller can write. Validate such a rule early, in plain
  Python, in `create()`/`write()` itself, reading the underlying data
  directly rather than through the compute.
- **When a shell reproduction and a real HTTP test disagree on identical
  code, suspect the framework layer around the code, not the code.** Fetch
  the RAW response body (bypassing any test helper's own interpretation)
  before adding more workarounds.
- **`env.cr.flush()` before querying a `_auto=False` SQL-view report model**
  whenever the query runs in the same transaction as an unflushed write — a
  raw SQL view sees only what has reached the table. Real HTTP requests
  never hit this (Odoo flushes and commits between requests); a one-session
  debugging script will.
- **A chatter `message_post()` call must be best-effort**, never able to
  undo the state change it is meant to be documenting — it can fail for
  reasons (no sender email configured) that have nothing to do with whether
  the action itself should succeed.
- **`max_cron_threads` must be ≥ 2** in production. The backlog snapshot,
  carry-forward, preventive-maintenance and alert crons all run overnight and
  would otherwise serialise behind one another.
- **The filestore and the database must be backed up together.** A database
  restored without its matching filestore loses every attachment.
- **The reverse proxy must forward `/websocket` to port 8072**, or Odoo 18's
  longpolling and live updates fail silently.
- **Shift C wraps midnight** (22:00–06:00). Duration and date attribution need
  explicit handling and explicit tests, including in a non-UTC company timezone.
- **A null target is not a zero target.** "No plan was set" and "we produced
  nothing" must display differently, or the reports mislead.
- **To modify another module's data records, use a `<function>`, not a
  `<record>`.** If the owning module declared them under `noupdate="1"`, Odoo
  skips every later declarative update silently.
- **XML comments may not contain `--`.** `--without-demo` and `----------`
  separators both break the parser.
- **`@api.constrains` only fires for fields present in the write.** An "at least
  one of these fields" rule needs a SQL `CHECK` as well.
- **A record rule cannot stop a write from *becoming* a value it forbids.**
  Rules filter which records a query touches, evaluated against the record as
  it is now — they do not see the proposed new values. A `write()` override
  checking `vals` explicitly is the only way to block "set this specific field
  to this specific value," e.g. locking who may set `state='approved'`.
- **`sudo()` is safe only after ownership is asserted, not before.** Call the
  authorisation check first (raise if it fails), and only `sudo()` the
  follow-up reads on a record that has already passed — never sudo the check
  itself.
- **Sass claims `min()`/`max()`/`clamp()` as its own functions and will refuse
  to mix units (e.g. `min(420px, 100%)`), failing the *entire* asset bundle
  compile** — not just the one rule. A stale cached `ir.attachment` can then
  keep serving the last-good bundle, so a passing "is my class name in the
  compiled CSS" check can be a false negative. Clear cached asset attachments
  and force a rebuild before trusting that check. Use two literal CSS
  declarations instead of the shorthand function.
- **Never use `docker compose exec` to run odoo.** It bypasses the image
  entrypoint (no `--db_*` arguments are built) and collides with the running
  server on port 8069. Use `docker compose run --rm web odoo ...`.
- **Docker commands fail in Git Bash on this machine** with
  `docker-credential-desktop: executable file not found`. Run them from
  PowerShell instead.
- **Odoo 18 has no `--admin-passwd` CLI option.** The master password can only
  live in a config file, which is why the dev placeholder is committed and the
  stack binds to 127.0.0.1.
- **Windows bind-mount performance** on `C:\` is poor — clone into the WSL 2
  filesystem.
- **An ACL grant and a record rule are independent, and a native module's own
  restrictive rule can silently defeat a grant we add ourselves.** Native
  `maintenance.equipment` restricts anyone without
  `maintenance.group_equipment_manager` to equipment they personally follow,
  regardless of what `ir.model.access.csv` allows. Check for existing record
  rules on any NATIVE model before assuming our own ACL row is the whole
  story — `grep` the owning addon's `security/*.xml`, not just its
  `ir.model.access.csv`.
- **When native `write()` re-derives a field as a side effect of another
  field changing, passing your own value for it in the SAME vals dict does
  not survive.** `maintenance.request.write()` re-stamps `close_date` to
  today whenever `stage_id` changes in the same call, discarding any
  explicit value given alongside it. A follow-up, separate write is the only
  reliable way to set such a field to something other than what native code
  would derive.
- **`tracking=True` on a field requires the model to inherit `mail.thread`**
  — Odoo only warns (not fails) when it does not, but it is dead
  configuration either way; remove it rather than leave the warning as noise.
- **`quick_add` is not a valid `<calendar>` view attribute in Odoo 18** —
  unlike the tracking warning above, this one DOES fail the install (a
  RelaxNG validation error against the view schema).
- **Grep the exact ID string before assigning a new sequential one**
  (assumption IDs, anything numbered by convention rather than by a real
  sequence). A sorted listing of all IDs surfaces GAPS, not COLLISIONS —
  Phase 6 silently reused an ID Phase 3 had already assigned, and a `sort -u`
  over sixty-plus rows did not catch it because both rows were syntactically
  valid, just semantically different things sharing one citation.
- **A fresh clone must set two things before its first commit** — both live in
  local `.git/config` and are therefore not carried by the clone:

  ```bash
  git config user.name  "sinchanakulkarni2112"
  git config user.email "323928844+sinchanakulkarni2112@users.noreply.github.com"
  git remote set-url origin git@github-sinchan:sinchanakulkarni2112/furnishing_mes.git
  ```

  This machine has two GitHub identities in `~/.ssh/config`. The default HTTPS
  credential and the plain `github.com` SSH host both authenticate as
  `shreyassridhar44`, which has no write access and returns 403. The
  `github-sinchan` alias uses `~/.ssh/github-sinchan` and authenticates as the
  repository owner.
