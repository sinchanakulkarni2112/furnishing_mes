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
