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

**D0.12 — Commit authorship is human-only.**
No AI author, co-author, trailer or footer anywhere. Recorded in `CLAUDE.md` §1
and `AGENTS.md`, and verified before every push.

### Open questions for later phases

| # | Question | Needed by |
|---|---|---|
| Q1 | Exact column layout of the customer's *DAY WISE OUTPUT* workbook | Phase 4 (importer) |
| Q2 | Real shift timings and break durations | Phase 2 |
| Q3 | Actual machine list, departments, and standard output rates | Phase 2 |
| Q4 | Alert thresholds the plant manager considers meaningful | Phase 11 |
| Q5 | ERP 10.8 API type and schema | Deferred integration |
| Q6 | Whether operators log in individually or share a machine PIN | Phase 4 |

Where these are unanswered, phases proceed on documented assumptions with
realistic mock data, and the assumption is recorded here.

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
- **Windows bind-mount performance** on `C:\` is poor — clone into the WSL 2
  filesystem.
