# 06 — Build Plan

The master delivery plan. Work proceeds **one phase at a time**, in order. Each
phase is a self-contained, demonstrable increment that ends with a commit and a
push to `origin/main`.

## How a Phase Runs

Say **"do phase N"**. The following happens, every time, without further prompting:

1. Re-read this phase's spec, the relevant design docs, and
   [`15-open-questions-and-assumptions.md`](15-open-questions-and-assumptions.md)
   — any assumption that has since been answered is corrected before the phase
   that depends on it.
2. Implement the deliverables.
3. Verify the exit criteria — the module must install/upgrade cleanly and all
   tests must pass.
4. Update `MEMORY.md` (decisions made), `15-open-questions-and-assumptions.md`
   (new assumptions adopted, questions raised or answered), `AGENTS.md` and
   `CLAUDE.md` if conventions changed, and tick this document's phase checklist.
5. Commit with a Conventional Commit message and push to `origin/main`.
6. Report what was built, what was verified, and what Phase N+1 will cover.

**Definition of Done — applies to every phase**

- [ ] `docker compose up -d` works from a clean clone
- [ ] `furnishing_mes` installs or upgrades with no errors and no warnings in the log
- [ ] All ACLs and record rules exist for every new model (no model ships without them)
- [ ] Odoo unit tests for the phase pass (`--test-enable`)
- [ ] Demo data loads, so the feature can be shown immediately
- [ ] Docs updated; traceability matrix rows for the phase marked complete
- [ ] Every value that stands in for an unanswered customer question is a
      **configuration record**, not hard-coded, and carries an assumption ID
- [ ] Committed and pushed with a meaningful message, authored by `sinchanakulkarni2112`

---

## Phase Map

| Phase | Title | Covers | Status |
|---|---|---|---|
| 0 | Documentation & Project Charter | — | ✅ Complete |
| 1 | Docker Foundation & Module Skeleton | R3.3 | ✅ |
| 2 | Master Data & Capacity Matrix | R1.2, R1.6, R3.2, R7.1 | ✅ |
| 3 | Production Planning Automation | R1 | ⬜ |
| 4 | Daily Tracking & Shop-Floor Terminal | R2, R3.1, R3.4, R3.5 | ⬜ |
| 5 | Downtime Management | R6 | ⬜ |
| 6 | Machine Utilisation & OEE | R5, R3.6 | ⬜ |
| 7 | Maintenance Management | R7 | ⬜ |
| 8 | Manpower & Resource Management | R8 | ⬜ |
| 9 | Backlog & Carry-Forward | R4 | ⬜ |
| 10 | Analytics & Dashboards | R9 | ⬜ |
| 11 | Alerts & Notifications | R10 | ⬜ |
| 12 | Reporting Suite | R12 | ⬜ |
| 13 | Customer Portal | Portal persona | ⬜ |
| 14 | Security Hardening, Testing & QA | Cross-cutting | ⬜ |
| 15 | Deployment, Documentation & Handover | Cross-cutting, R11 readiness | ⬜ |

Dependency chain: 1 → 2 → 3 → 4 → {5, 8} → 6 → 7 → 9 → 10 → 11 → 12 → 13 → 14 → 15.
Phases 5 and 8 both depend only on 4 and may be reordered if needed.

---

## Phase 0 — Documentation & Project Charter ✅

**Goal.** Establish the complete design before writing a line of business logic.

**Delivered**
- `docs/00` … `docs/14` — the full design set
- `README.md` — clone and run instructions
- `CLAUDE.md`, `AGENTS.md`, `MEMORY.md` — working conventions
- Odoo 18 Community capability audit (see `13-odoo-edition-constraints.md`)

**Commit.** `docs: add complete project documentation and phase-wise build plan`

---

## Phase 1 — Docker Foundation & Module Skeleton ✅

*Completed 2026-09-06 · module version `18.0.1.0.0`*

**Goal.** A reviewer clones the repo, runs one command, and logs into an Odoo
with an empty but installable `furnishing_mes` module.

**Deliverables**

1. `docker-compose.yml` — `web` (`odoo:18.0`) + `db` (`postgres:15`), named
   volumes `fmes-db-data` and `fmes-web-data`, bind mounts for `./addons` and
   `./config`, internal bridge network, `restart: unless-stopped`, healthcheck on
   `db` with `depends_on: condition: service_healthy`
2. `config/odoo.conf` — `addons_path`, database-manager policy, dev-friendly logging
3. `.env.example` and `.env` handling; `.gitignore` (`.env`, `*.pyc`,
   `__pycache__/`, `.idea/`, `.vscode/`, filestore artefacts)
4. `addons/furnishing_mes/` skeleton:
   - `__manifest__.py` with the full `depends` list, `license: LGPL-3`,
     `application: True`, version `18.0.1.0.0`
   - `__init__.py`, empty `models/`, `views/`, `security/`, `data/`, `demo/`,
     `static/`, `tests/` packages
   - `security/fmes_groups.xml` — the four-tier group hierarchy and module category
   - `security/ir.model.access.csv` — header, ready for rows
   - `views/menus.xml` — root **Furnishing MES** menu with placeholder sections
   - `static/description/icon.png` and `index.html`
5. `models/mixins.py` — `fmes.erp.sync.mixin` (fields only, no logic — the ERP seam)
6. `Makefile` (or `scripts/`) with `up`, `down`, `logs`, `restart`, `upgrade`,
   `test`, `shell`, `psql`
7. `tests/test_install.py` — asserts the module installs and the groups exist

**Exit criteria — all met**

| Criterion | Result |
|---|---|
| `docker compose up -d` from a clean clone brings up a working Odoo at `:8069` | ✅ `/web/login` and `/web/health` return 200 |
| The module appears in Apps and installs without error | ✅ `furnishing_mes` state `installed`, version `18.0.1.0.0` |
| The four role tiers exist with correct `implied_ids` | ✅ Operator → Internal User; Supervisor → Operator + MRP User + Equipment Manager; Plant Manager → Supervisor + MRP Manager + Stock Manager; Customer = `base.group_portal` |
| `make test` passes | ✅ 19 tests, 0 failed, 0 errors |
| No warnings on install or upgrade | ✅ clean at `--log-level=warn` |

**Deviations from the original spec**

1. **`list_db` is `True` in development, not `False`.** Odoo 18 has no
   `--admin-passwd` CLI option — the master password is a config-file setting
   only, so it cannot be injected from `.env`. Rather than ship a weak secret or
   an extra bootstrap script, the development stack binds to `127.0.0.1`, keeps
   the database wizard available, and states its placeholder master password
   openly in `config/odoo.conf`. Production sets `list_db = False` (Phase 15).
2. **Makefile targets use `docker compose run`, not `exec`.** `exec` bypasses the
   image entrypoint (so no `--db_*` arguments are built) and collides with the
   running server on port 8069. `run --rm` avoids both and still allows HTTP
   inside the container for the `HttpCase` tests later phases will add.
3. **The `PG*` libpq variables were added to the `web` service** so that an
   `exec`'d Odoo can still reach the database, without writing any credential
   into the committed `config/odoo.conf`.
4. **One working menu leaf was added** (Configuration → Machines, pointing at
   `mrp.workcenter`) so the application is navigable from Phase 1. Odoo hides
   parent menus that have no visible children, so an entirely empty skeleton
   would have been invisible after install.

**Commit.** `feat: add dockerised odoo 18 stack and furnishing_mes module skeleton`

---

## Phase 2 — Master Data & Capacity Matrix ✅

*Completed 2026-09-06 · module version `18.0.2.0.0`*

**Goal.** Every master record the planning engine will need, plus the mock ERP
dataset that stands in for ERP 10.8.

**Deliverables**

1. `fmes.shift` — model, views (list/form), menu, demo shifts A/B/C
2. `mrp.workcenter` extension — machine code, `department_id`, `equipment_id`
   bridge, `fmes_std_manpower`, criticality, bottleneck flag; extended form and
   a machine-master kanban
3. `maintenance.equipment` extension — `workcenter_id` inverse, criticality;
   automatic two-way consistency between the bridge fields
4. `fmes.capacity.matrix` — model with `std_output_per_hour` normalisation,
   overlap constraint, list/form views, and an editable grid grouped by machine
5. `mrp.workcenter.productivity.loss` extension + `data/loss_reasons.xml`
   seeding all ten downtime categories with correct `loss_type`
6. `data/ir_sequence.xml` — all sequences from the data-model doc
7. **Mock ERP dataset** in `demo/` — customers (`res.partner`), item master
   (`product.template`), BOMs (`mrp.bom`), sales orders (`sale.order`),
   manufacturing orders (`mrp.production`), departments, work centers,
   equipment, and a populated capacity matrix. Sized to a realistic furnishing
   plant: ~4 departments, ~12 machines, ~20 items, ~30 open orders
8. XLSX/CSV import templates in `docs/templates/` for shifts, machines and the
   capacity matrix
9. ACLs and record rules for every new model

**Exit criteria — all met**

| Criterion | Result |
|---|---|
| A Plant Manager can maintain all masters through the UI | ✅ Shifts, Machines, Capacity Matrix, Equipment, Departments and Downtime Reasons under Configuration |
| Demo data loads cleanly and shows a plausible plant | ✅ 6 departments, 3 shifts, 15 machines (all bridged to equipment both ways), 20 items in 4 families, 20 BOMs, 8 customers, 30 sales orders, 30 manufacturing orders, 40 capacity rows |
| Capacity matrix resolves product → category correctly | ✅ unit-tested, including the category-tree walk |
| Tests pass | ✅ 68 tests, 0 failed, 0 errors |
| No warnings on install or upgrade | ✅ clean at `--log-level=warn`, verified on a fresh database too |

**Deviations from the original spec**

1. **A missing capacity rate resolves to 0.0, not to `workcenter.default_capacity`.**
   The data-model doc originally proposed falling back to the work center's
   default capacity. That field means "pieces produced in parallel", not an
   hourly rate, so using it would produce plausible-looking plans built on an
   unrelated number. A missing rate is now visible to the planner instead.
   `docs/03-data-model.md` corrected.
2. **Odoo's own loss reasons are classified from a `<function>` call, not
   `<record>` tags.** `mrp` ships them inside a `noupdate="1"` block, which sets
   `ir.model.data.noupdate` on the records — so any later declarative update is
   skipped silently, whatever our own data block says. Found by a failing test.
3. **The capacity matrix carries a `basis_hours` field.** Plants quote rates per
   shift or per day as often as per hour; normalising to an hourly rate needs to
   know how many hours the basis represents, and guessing it would be wrong.

**Commit.** `feat(masters): add shift, machine, capacity matrix and mock plant dataset`

---

## Phase 3 — Production Planning Automation

**Goal.** Requirement 1 in full — the system generates capacity-aware,
machine-wise, shift-wise plans without Excel.

**Deliverables**

1. `fmes.production.plan` + `fmes.production.plan.line` models, states, sequences
2. `services/planning_engine.py` — `fmes.planning.engine` AbstractModel:
   - **Demand collection** — open manufacturing orders, optionally sales orders,
     ordered by deadline then priority
   - **Capacity computation** — per machine per shift:
     `net_shift_hours × efficiency_factor × availability_factor`, where
     availability derates for scheduled maintenance windows and historic
     unplanned downtime
   - **Manpower constraint** — a machine is only loadable if allocated manpower
     meets `std_manpower`; otherwise capacity is scaled down proportionally
   - **Allocation** — greedy earliest-due-date first, respecting machine
     eligibility from the capacity matrix, `priority` preference, changeover
     minutes when switching products, and bottleneck-first sequencing
   - **Carry-forward hook** — unfinished quantity from previous plans enters
     demand ahead of new orders
3. `wizards/plan_generator.py` — the wizard the planner actually uses: date
   range, plan type, departments, demand source, strategy; produces a plan in
   `draft` with a preview of capacity utilisation
4. **Scheduling Board** — OWL client action: machines on Y, dates/shifts on X,
   colour-coded load, over-capacity highlighted, drag to reassign, click to open
   the line. Replaces the Enterprise Gantt (ADR-003)
5. Views: plan form with line editor, machine-wise and shift-wise grouped views,
   pivot of planned load vs capacity
6. `plan.action_confirm()` / `action_release()` — releasing a plan creates or
   updates the corresponding `mrp.workorder` schedule dates
7. XLSX export of the released plan
8. Tests: capacity maths, overload rejection, changeover accounting,
   carry-forward inclusion, deterministic output for a fixed dataset

**Exit criteria**
- A planner generates a week's plan for 12 machines in one wizard run
- No plan line exceeds its machine's available capacity for that shift
- The board renders the plan and reflects edits

**Commit.** `feat(planning): add capacity-aware production planning engine and scheduling board`

---

## Phase 4 — Daily Tracking & Shop-Floor Terminal

**Goal.** Requirement 2 and the real-time half of Requirement 3.

**Deliverables**

1. `fmes.production.entry` — full model, computes, constraints, approval
   workflow (`draft → submitted → approved`), immutability after approval
2. Auto-creation of entries from released plan lines (cron at shift start)
3. **Shop-Floor Terminal** — OWL client action at `/fmes/terminal`:
   - Operator selects their machine (restricted by today's allocation)
   - Large touch targets, minimal chrome, readable at arm's length
   - Shows assigned work orders, target quantity, elapsed time
   - Start / pause / stop with live timer writing `mrp.workcenter.productivity`
   - Quantity entry with a numeric keypad; reject quantity capture
   - One-tap downtime with reason picker (wired fully in Phase 5)
   - Submit for supervisor approval
   - `controllers/shopfloor.py` — JSON endpoints with server-side authorisation
     on every call
4. Supervisor approval queue — list view with bulk approve/reject
5. Planned vs actual views: date-wise, shift-wise, machine-wise, department-wise;
   variance and achievement % with conditional colour
6. Live production status board — machine kanban with real-time state colouring
7. `wizards/production_import.py` — **DAY WISE OUTPUT importer**: upload the
   customer's XLSX, map columns, validate, preview errors, commit as a batch
   (`fmes.import.batch`) that can be reversed
8. Tests: achievement computation, uniqueness constraint, approval immutability,
   operator scoping, importer round-trip

**Exit criteria**
- An operator records a shift's output on a tablet without touching the backoffice
- A supervisor approves the shift and the daily report reflects it
- A historical DAY WISE OUTPUT sheet imports without manual cleanup

**Commit.** `feat(execution): add daily production tracking, shop-floor terminal and excel importer`

---

## Phase 5 — Downtime Management

**Goal.** Requirement 6.

**Deliverables**

1. `mrp.workcenter.productivity` extension — shift, entry link, category,
   remarks, reporter, approval state, maintenance escalation link
2. Terminal downtime flow completed — reason picker grouped by category, running
   downtime timer, mandatory remark for `other`
3. Supervisor downtime approval queue; rejecting returns it to the operator
4. Auto-escalation — a loss reason flagged `fmes_requires_maintenance` creates a
   `maintenance.request` linked back to the downtime event
5. `fmes.downtime.report` SQL view
6. Analysis views: pivot by category × machine × shift, Pareto graph of loss
   hours, trend line, drill-through to events
7. Downtime hours flow into `fmes.production.entry.downtime_hours` automatically
8. Tests: duration maths, category rollup, escalation, OEE consistency with
   Odoo's native computation

**Exit criteria**
- Every downtime minute carries a coded reason; no uncategorised bucket
- Pareto view identifies the top three loss reasons for a period

**Commit.** `feat(downtime): add digital downtime capture, approval and loss analysis`

---

## Phase 6 — Machine Utilisation & OEE

**Goal.** Requirement 5 and Requirement 3.6.

**Deliverables**

1. `services/utilization_service.py` — availability, performance and quality
   factors; utilisation % = run hours ÷ available hours
2. `fmes.utilization.report` SQL view
3. `mrp.workcenter.fmes_utilization_pct` and `fmes_current_state` computes
4. Standard vs actual output comparison, sourced from the capacity matrix
5. Under-utilised machine detection — configurable threshold, list and dashboard tile
6. Bottleneck analysis — load vs capacity ranking; auto-suggest `fmes_is_bottleneck`
7. OEE views built on Odoo's native `mrp.workcenter.oee`, with our downtime
   categories feeding the availability factor correctly
8. Tests: utilisation maths against a fixture shift, bottleneck ranking order

**Exit criteria**
- Utilisation % is available per machine per day and per month
- The three least-utilised and top-three bottleneck machines are identifiable in one view

**Commit.** `feat(utilization): add machine utilisation, efficiency and bottleneck analysis`

---

## Phase 7 — Maintenance Management

**Goal.** Requirement 7.

**Deliverables**

1. `fmes.maintenance.schedule` + `fmes.maintenance.checklist.line`
2. Cron `fmes_generate_preventive_requests` — creates `maintenance.request`
   records `lead_time_days` before `next_due_date`; recomputes `next_due_date`
   on completion
3. Usage-based triggering from accumulated run hours
4. `maintenance.request` extension — work center, downtime link, cost, checklist
   results; breakdown requests raised from downtime carry the lost hours
5. Equipment health score compute (MTBF, overdue PMs, recent breakdown frequency)
6. Maintenance calendar and kanban; equipment history view
7. `fmes.maintenance.report` SQL view — PM vs breakdown split, MTBF, MTTR, cost,
   downtime hours by month and equipment
8. Maintenance KPI dashboard section
9. Tests: schedule recurrence, lead-time generation, no duplicate open requests,
   MTBF/MTTR sanity

**Exit criteria**
- Preventive requests appear automatically before due dates
- A breakdown logged on the terminal produces a maintenance request with the
  correct machine, downtime and reporter

**Commit.** `feat(maintenance): add preventive scheduling, breakdown tracking and maintenance kpis`

---

## Phase 8 — Manpower & Resource Management

**Goal.** Requirement 8.

**Deliverables**

1. `fmes.manpower.log` — standard vs actual, absence, shortage, utilisation
2. `fmes.operator.allocation` — roster by date/shift/employee/machine, with the
   uniqueness constraint that also backs the operator record rule
3. Roster planning view (calendar + list) for supervisors; bulk copy-previous-week
4. `res.users.fmes_allowed_workcenter_ids` compute that drives operator scoping
5. Manpower impact analysis — correlation of shortage % against achievement %
   per department and shift
6. Feedback into the planning engine: allocated manpower now derates capacity
7. Manpower views and dashboard tiles
8. Tests: shortage maths, allocation uniqueness, capacity derating

**Exit criteria**
- Tomorrow's roster is planned in the system, not on paper
- Manpower shortage is visible next to the production shortfall it caused

**Commit.** `feat(manpower): add operator allocation, manpower logging and impact analysis`

---

## Phase 9 — Backlog & Carry-Forward

**Goal.** Requirement 4.

**Deliverables**

1. `fmes.backlog.snapshot` model (cron-written, UI read-only)
2. Cron `fmes_backlog_snapshot` — nightly; classifies each open order as
   pending / blocked / delayed / at-risk / completed and records pending quantity
3. `services/backlog_service.py` — classification rules, criticality scoring
4. Blocking workflow — a supervisor marks an order blocked with a reason; the
   block propagates to the plan and excludes the order from auto-scheduling
5. Cron `fmes_carry_forward` — unfinished released plan lines roll into the next
   working day with `source='carry_forward'` and a link to the origin line
6. Backlog trend graph (quantity and count over time), ageing buckets
   (0–3 / 4–7 / 8–15 / 15+ days)
7. Delayed-order list with days-delayed and responsible department
8. Tests: snapshot idempotency, classification boundaries, carry-forward
   quantity conservation (nothing lost or duplicated)

**Exit criteria**
- Backlog quantity and trend for the last 30 days is available without manual work
- Yesterday's shortfall appears in today's plan automatically

**Commit.** `feat(backlog): add backlog snapshots, blocking workflow and carry-forward automation`

---

## Phase 10 — Analytics & Dashboards

**Goal.** Requirement 9, all ten metrics.

**Deliverables**

1. `fmes.production.report` SQL view (if not already created in Phase 4) plus
   final tuning of all four read models and their indexes
2. **Executive Dashboard** — OWL client action:
   - KPI row: achievement %, utilisation %, downtime %, OEE, backlog quantity,
     open maintenance
   - Trend charts: production trend, utilisation trend, downtime trend
   - Comparison charts: department performance, shift performance
   - Pareto: downtime loss reasons
   - Capacity utilisation gauge, backlog ageing, maintenance performance
   - Global date-range and department filters; every tile drills through to the
     underlying records
3. Role-scoped dashboard variants: Plant Manager (plant-wide) and Supervisor
   (own departments)
4. Native pivot and graph views on every report model for ad-hoc analysis
5. `spreadsheet_dashboard` boards for management self-service
6. Performance: verify the dashboard renders under 2 s against a 100k-row dataset
7. Tests: each KPI computed by the dashboard equals the same figure from the
   underlying records

**Exit criteria**
- Every one of the ten requested management metrics is on screen
- The dashboard loads in under two seconds on the seeded dataset

**Commit.** `feat(analytics): add executive dashboard and production analytics read models`

---

## Phase 11 — Alerts & Notifications

**Goal.** Requirement 10.

**Deliverables**

1. `fmes.alert.rule` and `fmes.alert` models
2. `services/alert_engine.py` — evaluates rules, applies scope and cooldown,
   raises alerts, dispatches to activity / Discuss / email
3. Cron `fmes_evaluate_alerts` (every 15 minutes) for threshold-based rules;
   `base_automation` triggers for event-based rules (breakdown, block)
4. Default rules seeded in `data/alert_rules.xml` for all seven required types
5. `mail.template` per alert type, with a clean HTML layout
6. **Alert Center** — list and kanban by severity, acknowledge and resolve
   actions, unread counter in the systray
7. Escalation — a critical alert unacknowledged past its window notifies the
   Plant Manager
8. Tests: threshold boundaries, cooldown suppression, scope filtering, recipient
   resolution, no duplicate alerts for one condition

**Exit criteria**
- Each of the seven alert types fires correctly on a seeded trigger condition
- No alert storm: repeated conditions respect cooldown

**Commit.** `feat(alerts): add rule-driven alert engine, notifications and alert center`

---

## Phase 12 — Reporting Suite

**Goal.** Requirement 12, all ten reports.

**Deliverables**

1. QWeb PDF templates with a shared branded layout (header, plant, period,
   generated-on, page numbers) for:
   Daily Production · Machine Utilisation · Production Output Summary ·
   Downtime · Backlog · Carry Forward Order · Maintenance · Productivity ·
   Exception · Monthly Management MIS
2. XLSX export for each, via `xlsxwriter` (already bundled with Odoo)
3. `wizards/report_export.py` — common parameter wizard (date range, department,
   machine, shift, format)
4. Scheduled delivery — `fmes.report.schedule` records driving a cron that emails
   the chosen reports to chosen recipients daily / weekly / monthly
5. Monthly MIS pack — a composite multi-section PDF for management
6. Exception report — consolidated variance and threshold breaches for the period
7. Tests: each report renders for the demo dataset without error; figures
   reconcile with the dashboard

**Exit criteria**
- All ten named reports produce correct PDF and XLSX output
- The daily production report can be scheduled to arrive by email each morning

**Commit.** `feat(reporting): add complete pdf and xlsx report suite with scheduled delivery`

---

## Phase 13 — Customer Portal

**Goal.** The Customer persona.

**Deliverables**

1. Portal user provisioning documented and demo portal users seeded
2. `/my/home` extension — order count and open ticket tiles
3. `/my/orders` — the customer's own orders with production progress %, expected
   completion, and status; strictly `partner_id`-filtered
4. Order detail page — line-level progress derived from linked manufacturing
   orders, without exposing internal machine, cost or downtime data
5. `fmes.support.ticket` — model, portal create form, thread, status tracking
6. `/my/tickets` — list and detail with reply
7. Internal ticket handling views for supervisors and managers
8. Branded, responsive portal templates consistent with the backoffice design
9. Tests: cross-customer access denial, portal user cannot reach `/web`, ticket
   ownership

**Exit criteria**
- A portal customer logs in, sees only their orders, and raises a ticket
- No internal data (cost, machine, downtime, other customers) is reachable

**Commit.** `feat(portal): add customer order tracking and support ticket portal`

---

## Phase 14 — Security Hardening, Testing & QA

**Goal.** Make it production-grade rather than merely feature-complete.

**Deliverables**

1. Full ACL and record-rule audit — every model, every group, no gaps; the
   Phase 4 permission matrix verified line by line
2. `tests/test_security.py` — all ten checks from the security document
3. Test-coverage sweep across all services; target ≥ 80 % on `services/` and
   model compute methods
4. Performance dataset generator (`scripts/seed_load.py`) producing ~100k
   production entries, ~50k downtime events; dashboard and report timings recorded
5. Index review against `EXPLAIN ANALYZE` on the heaviest report queries
6. Input validation sweep — constraints on every quantity, date and percentage field
7. Odoo log review at `--log-level=warn` — zero warnings on install and upgrade
8. Dependency and image review; pin the Odoo image digest for reproducibility
9. Backup and restore rehearsal — full drill documented with timings
10. `docs/10-testing-qa.md` updated with actual results

**Exit criteria**
- Every security test passes
- Dashboard under 2 s and reports under 10 s on the 100k-row dataset
- A restore from backup reproduces the system exactly

**Commit.** `test: add security, performance and integration test suites`

---

## Phase 15 — Deployment, Documentation & Handover

**Goal.** Ship it, and leave it maintainable.

**Deliverables**

1. `docker-compose.prod.yml` — production overrides: multi-worker Odoo,
   `proxy_mode`, resource limits, log rotation, pinned image digests
2. Reverse proxy and TLS guidance (Nginx or Caddy sample config, kept outside the
   default stack)
3. Backup automation — `scripts/backup.sh` (`pg_dump` + filestore) and
   `scripts/restore.sh`, with a cron example
4. Monitoring and health checks; log aggregation guidance
5. Upgrade runbook — module upgrade, Odoo minor upgrade, rollback
6. **User manuals** — one per persona (Operator, Supervisor, Plant Manager,
   Customer) in `docs/manuals/`, screenshot-illustrated
7. **Administrator guide** — master data setup, alert tuning, user onboarding
8. Final README pass; architecture diagrams regenerated if drifted
9. **ERP 10.8 integration readiness review** — confirm the seam is intact,
   finalise the field mapping table, and estimate the connector effort
10. Handover checklist and known-limitations register

**Exit criteria**
- A fresh on-prem server is brought to a working production instance by following
  the deployment doc alone
- Each persona has a manual covering their daily tasks
- The ERP integration effort is specified and estimated

**Commit.** `docs: add deployment runbook, user manuals and erp integration readiness review`

---

## Risk Register

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| RK1 | Enterprise-only features assumed available | High | Audited up front; ADR-002/003 build replacements. See `13-odoo-edition-constraints.md` |
| RK2 | Real customer master data differs from mock | Medium | Importer with column mapping; mock data isolated in `demo/` and never in `data/` |
| RK3 | Planning engine output disputed by planners | Medium | Engine is deterministic and explainable; every plan line records why it was placed. Manual override always allowed |
| RK4 | Operator adoption of the terminal | High | Tablet-first UI, minimal taps, offline-tolerant submit, PIN handover |
| RK5 | Dashboard slows as history grows | Medium | SQL views + indexes from day one; materialised-view escalation path in Phase 14 |
| RK6 | ERP 10.8 API unknown | Medium | Deferred by agreement; adapter pattern keeps the domain untouched |
| RK7 | Scope creep across 15 phases | Medium | Phase gates; nothing outside a phase's deliverable list is built in that phase |
