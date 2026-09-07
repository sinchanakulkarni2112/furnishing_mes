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
| 3 | Production Planning Automation | R1 | ✅ |
| 4 | Daily Tracking & Shop-Floor Terminal | R2, R3.1, R3.4, R3.5 | ✅ |
| 5 | Downtime Management | R6 | ✅ |
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

## Phase 3 — Production Planning Automation ✅

*Completed 2026-09-06 · module version `18.0.3.0.0`*

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

**Exit criteria — all met**

| Criterion | Result |
|---|---|
| A planner generates a week's plan in one wizard run | ✅ 153 demands → 246 plan lines across 15 machines and 3 shifts |
| No plan line exceeds its machine's capacity for that shift | ✅ **0 capacity breaches**, verified on the demo plant and unit-tested as the engine's core invariant |
| The board renders the plan and reflects edits | ✅ board data API tested; SCSS and OWL component verified to compile into the backend bundle |
| Tests pass | ✅ 115 tests, 0 failed, 0 errors |
| No warnings on install or upgrade | ✅ clean at `--log-level=warn` on a fresh database |

**Deviations from the original spec**

1. **The manpower factor is a working hook returning 1.0, not a live
   constraint.** The mechanism is in place and applied to every capacity
   calculation, but the roster it would read arrives with operator allocation in
   Phase 8. Building a half-real constraint against a model that does not exist
   yet would have been worse than an honest, tested placeholder — Phase 8
   replaces one method body and nothing else in the engine changes.
2. **Routing operations were added to the demo bills of materials.** Without
   them a manufacturing order has no work orders, so there is no machine-wise
   schedule to build and nothing for the Phase 4 terminal to show. Odoo creates
   the work orders automatically because `workorder_ids` is a stored compute.
3. **Plan release also sets manufacturing order dates**, not only work order
   dates, so orders whose bill of materials has no routing are still scheduled.

**Commit.** `feat(planning): add capacity-aware production planning engine and scheduling board`

---

## Phase 4 — Daily Tracking & Shop-Floor Terminal ✅

*Completed 2026-09-06 · module version `18.0.4.0.0`*

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

**Exit criteria — all met**

| Criterion | Result |
|---|---|
| An operator records a shift's output on a tablet without the backoffice | ✅ OWL terminal with machine picker, numeric keypad and one-tap submit; every endpoint re-authorises server-side |
| A supervisor approves the shift and it reaches the reports | ✅ approval queue; only approved entries reach reporting views |
| A DAY WISE OUTPUT sheet imports without manual cleanup | ✅ header detection, guessed column mapping, row-level validation, reversible batch |
| Tests pass | ✅ 169 tests, 0 failed, 0 errors |
| No warnings on install or upgrade | ✅ clean at `--log-level=warn` on a fresh database |

End-to-end on the demo plant: plan released (246 lines) → 82 entries generated
(idempotent on re-run) → output recorded → submitted and approved → 61 plan
lines `done`, 21 `partial` → the shortfall carried into the next plan → approved
figures refused further edits.

**Deviations from the original spec**

1. **Operator scoping is by machine assignment, not the daily roster.**
   `fmes.operator.allocation` arrives in Phase 8. Assignment on the user is
   real scoping that works today and stays useful afterwards — a permanent
   assignment and a day's allocation are different things. An unassigned
   operator is not locked out but sees only their own entries.
2. **No per-operator PIN (assumption A16).** Operators authenticate with a
   normal Odoo login. A PIN is a second authentication mechanism to build and
   secure, and individual logins give a stronger audit trail. Question Q12 is
   still open; if the plant wants shared sessions, the PIN layers on top of
   what is here.
3. **Downtime is captured as hours, not yet as coded events.** The terminal has
   a downtime field feeding `downtime_hours`; Phase 5 replaces it with reason-
   coded events and recomputes the field from them.
4. **The live status board is a kanban, not an OWL component.** Odoo's kanban
   already does auto-refresh, grouping and drill-through; a custom component
   would have been more code for less.

**Commit.** `feat(execution): add daily production tracking, shop-floor terminal and excel importer`

---

## Phase 5 — Downtime Management ✅

*Completed 2026-09-07 · module version `18.0.5.0.0`*

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

**Exit criteria — all met**

| Criterion | Result |
|---|---|
| Every downtime minute carries a coded reason; no uncategorised bucket | ✅ enforced in `create()`/`write()`, not just the UI — verified by a test that a reason lacking a category is refused |
| Pareto view identifies the top three loss reasons for a period | ✅ `fmes.downtime.report` pivot/graph, grouped by category and machine |
| Tests pass | ✅ 216 tests, 0 failed, 0 errors |
| No warnings on install, with or without demo data | ✅ verified on three fresh databases: with demo data, and explicitly `--without-demo=all` |

End-to-end on the demo plant: a plan released and entries generated → coded
downtime logged on six entries, one auto-escalating to a maintenance request →
`downtime_hours` rolled up onto the entry automatically → entries and downtime
both submitted and approved → approved downtime refused a further edit →
`fmes.downtime.report` showed 3.25 hours across the coded events → a rejected
event, edited by the operator who logged it, correctly returned to draft.

**Deviations and findings — four real bugs, caught by actually running the
code rather than only asserting against it in isolation**

1. **Every machine defaulted to the company's Mon–Fri business-hours calendar,
   which silently zeroed downtime duration outside those hours.** Odoo's
   native `mrp.workcenter.productivity.duration` compute calls
   `loss_id._convert_to_duration()`, which for a non-productive loss type on a
   work center *with* a `resource_calendar_id` computes duration from that
   calendar's working hours, not wall-clock elapsed time. A three-shift plant
   is down for stretches of every 24 hours that calendar knows nothing about —
   a night-shift stoppage computed to exactly 0.0 minutes. Fixed by defaulting
   `resource_calendar_id` to empty on `mrp.workcenter`, since this module's
   capacity model is `fmes.shift`, never Odoo's resource calendar. Affected
   every machine created since Phase 2.
2. **Field-level `groups=` blocked an operator's write even when only
   *clearing* a restricted field to `False`.** The auto-revert-to-draft path
   (editing a rejected event returns it to draft) included the
   supervisor-only `fmes_approved_by`/`fmes_approved_on` fields in its own
   vals just to clear them, which Odoo refuses regardless of the value.
   Fixed by stamping or clearing those two fields in a separate `sudo()`
   write, decoupled from the caller's own vals.
3. **Supervisors and managers were caught by the operator's own restrictive
   record rules**, because Phase 1's cumulative role hierarchy
   (`implied_ids`) means a Supervisor *is*, transitively, an Operator too.
   Odoo evaluates a non-global `ir.rule` against every group a user belongs
   to, including implied ones, and with no other non-global rule on this
   model to widen it back out, the operator's restriction silently applied to
   everyone above them as well. Fixed with an explicit, unrestricted rule for
   `group_fmes_supervisor` — the same pattern Phase 4 already used for
   `fmes.production.entry`, missed here on the assumption that the native
   `mrp.group_mrp_user` ACL alone would be enough (it grants the base
   permission; it does not exempt anyone from an `ir.rule` domain).
4. **`@api.constrains` on a computed field is not reliable enough for a
   caller to catch.** Both downtime-categorisation rules read `fmes_category`,
   a stored related field. On a model with `mail.thread`'s tracking enabled,
   Odoo can defer that field's recompute-and-validate cycle past
   `create()`/`write()` returning, to the *next* flush — which, for a
   JSON-RPC controller, is the HTTP layer's own post-dispatch
   `env.cr.flush()`, entirely outside any try/except the controller can
   write. A downtime/start request correctly caught and returned
   `{'ok': False, ...}` for this exact violation, and *still* surfaced an
   uncaught `ValidationError` moments later, traced via the raw response body
   to `mail_thread.py`'s own `_compute_field_value` calling
   `_validate_fields`. Fixed by validating both rules early and
   synchronously in `create()`/`write()`, reading the loss reason directly
   rather than through the computed field, so the check needs no flush and
   cannot be deferred. The `api.constrains` versions stay as a backstop.
   *Generalisable: never rely on `api.constrains` alone for a rule a calling
   layer must be able to catch reliably, once a computed field and
   `mail.thread` tracking are both in play — validate early in plain Python
   instead.*
5. A fifth, smaller finding: `action_reject()`'s chatter note is now
   best-effort (wrapped, never allowed to undo an otherwise-successful
   rejection) after it surfaced that a user with no email configured could
   not reject a downtime event at all, since `message_post()` requires one.

**Commit.** `feat(downtime): add digital downtime capture, approval and loss analysis`

---

## Phase 6 — Machine Utilisation & OEE ✅

*Completed 2026-09-07 · module version `18.0.6.0.0`*

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
8. **Mirror `fmes.production.entry.run_hours` into a `loss_type='productive'`
   `mrp.workcenter.productivity` record on approval.** Confirmed necessary in
   Phase 5: native OEE is `productive_time / (productive_time + blocked_time)`,
   and our system logs only the loss (downtime) side of that ratio through
   Phase 5 — nothing yet writes the productive side, so every machine's native
   OEE reads as 0% however much downtime is correctly coded. This is not a
   Phase 5 defect (ADR-001/D5.4's own "OEE consistency" test is intentionally
   narrower: it proves downtime we log correctly *reduces* OEE once productive
   time exists, not that productive time gets logged automatically) — it is
   the specific piece of wiring that makes native OEE meaningful, and it
   belongs here, once run_hours has a settled definition to mirror from.
9. Tests: utilisation maths against a fixture shift, bottleneck ranking order,
   and native OEE reading a real, non-zero value once run_hours is mirrored

**Exit criteria — all met**

| Criterion | Result |
|---|---|
| Utilisation % is available per machine per day and per month | ✅ `fmes.utilization.report` (date × shift × machine grain, pivoted to week/month) and `mrp.workcenter.fmes_utilization_pct` (rolling 30 days) |
| The three least-utilised and top-three bottleneck machines are identifiable in one view | ✅ `fmes.utilization.service._under_utilized_machines()` / `_rank_by_utilization()`, backing the machine kanban badge, the under/over-loaded search filters, and the "Suggest Bottlenecks" bulk action |
| Tests pass | ✅ 235 tests, 0 failed, 0 errors |
| No warnings on install, with or without demo data | ✅ verified on the dev database and a fresh `--without-demo=all` database |

End-to-end on the demo plant: before this phase, a demo machine's native `oee`
read `0.0` (Phase 5's known gap, D5.6). Approving a production entry with
`run_hours=3.0` against it mirrored a productive-time log and native `oee`
immediately read `100.0` (a clean run, no downtime in the window) —
`fmes_utilization_pct` read `40.0` (3 of 7.5 net shift hours). Running
`_suggest_bottlenecks()` against the demo plant correctly cleared three
machines that demo data had pre-flagged `fmes_is_bottleneck` by hand but whose
current rolling utilisation no longer clears the 90% threshold — the
recompute is a deterministic function of current data, not a one-time label.

**Deviations and findings**

1. **A raw SQL view (`_auto = False`) does not benefit from the ORM's usual
   auto-flush before `search()`.** A test approving a production entry and
   immediately reading `fmes.utilization.report` as a different user
   intermittently found no rows, because the entry's own pending writes (and
   the productive-time mirror `_fmes_sync_productive_time()` creates) were
   still only in the ORM's cache, not yet in the tables the view's SQL reads
   directly. A regular model's `search()` flushes the fields it depends on
   automatically; a hand-written view query has no such dependency graph to
   flush against. Fixed by calling `self.env.flush_all()` explicitly before
   every test that reads the view — the same discipline `fmes.downtime.report`
   already required in Phase 5, now applied consistently here too.
2. The SQL view's own docstring initially claimed a downtime event logged with
   no linked production entry would still surface as its own row (via the
   `FULL OUTER JOIN`). In fact `fmes_shift_id` is a *related* field off
   `fmes_entry_id` (Phase 5), so an entry-less event has no shift to place it
   in, and the shift-grained view necessarily excludes it — corrected the
   comment to say so rather than leave a claim the SQL doesn't keep; that
   event still counts toward the machine's own MTBF/MTTR once Phase 7 adds it.

**Commit.** `feat(utilization): add machine utilisation, efficiency and bottleneck analysis`

---

## Phase 7 — Maintenance Management ✅

*Completed 2026-09-07 · module version `18.0.7.0.0`*

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

**Exit criteria — all met**

| Criterion | Result |
|---|---|
| Preventive requests appear automatically before due dates | ✅ `_cron_generate_due_requests` raises a request `lead_time_days` ahead of `next_due_date`; verified idempotent (a second cron run on the same day raises nothing new) |
| A breakdown logged on the terminal produces a maintenance request with the correct machine, downtime and reporter | ✅ `_fmes_escalate_if_required` (Phase 5) now also stamps `workcenter_id` and `fmes_productivity_id`; `fmes_downtime_hours` tracks the event's own live duration |
| Tests pass | ✅ 268 tests, 0 failed, 0 errors |
| No warnings on install, with or without demo data | ✅ verified on the dev database and a fresh `--without-demo=all` database |

End-to-end on the demo plant: a schedule's `last_done_date` moved back to put
it inside its own lead-time window → the cron raised exactly one preventive
request, a second cron run raised nothing further → marking that request done
moved `last_done_date` forward and recomputed `next_due_date` a month out →
a breakdown logged against the same machine created a corrective request
carrying its work center and a live downtime figure (0.0 h running, ~0.22 h
once stopped) → the equipment's health score read 92 (100 minus the 8-point
penalty for that one recent breakdown) → the KPI report showed 6 equipment/
month rows, reading `mtbf`/`mttr` straight off the native equipment fields.

**Deviations and findings**

1. **Native `maintenance.equipment` carries its own restrictive record rule**
   (`maintenance/security/maintenance.xml`, `equipment_rule_user`) limiting
   anyone without `maintenance.group_equipment_manager` to equipment they
   personally follow. Supervisors/managers are exempt (that group is implied
   by `group_fmes_supervisor`, Phase 1) — operators are not, so a test proving
   an operator could compute `fmes_health_score` on a machine they do not
   follow failed with an `AccessError`, even though our own ACL grants
   operators plain read access to the model. Fixed by having the health-score
   compute read `mtbf`, `expected_mtbf`, `fmes_schedule_ids` and
   `maintenance_ids` through `equipment.sudo()` — the score is a read-only
   0-100 summary, not the underlying rows, so it should not depend on
   follower status. `_compute_fmes_current_state` (Phase 2/4) reads
   `maintenance.request` the same non-sudo way and is likely exposed to the
   same gap for an operator viewing a machine they have no request history
   on; out of this phase's scope to touch, logged in MEMORY.md for whoever
   next touches operator-facing machine status (a natural fit for Phase 11's
   alert work).
2. **Native `maintenance.request.write()` re-stamps `close_date` to the real
   "today" whenever `stage_id` is in the same vals dict, silently overriding
   any explicit `close_date` passed alongside it.** A PM-compliance test
   backdating a request's close date to prove an on-time closure passed for
   the wrong reason at first (the real test-run date happened to still read
   as "late" by coincidence) before this was caught and fixed with a second,
   separate write for the backdated value.
3. The SQL view needed its own `has_pm_due` boolean, the same null-handling
   pattern Phase 4's `has_target` already established: a month with no PM due
   for a machine must read as "—", not a misleading 0% compliance.

**Commit.** `feat(maintenance): add preventive scheduling, breakdown tracking and maintenance kpis`

---

## Phase 8 — Manpower & Resource Management ✅

*Completed 2026-09-07 · module version `18.0.8.0.0`*

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

**Exit criteria — all met**

| Criterion | Result |
|---|---|
| Tomorrow's roster is planned in the system, not on paper | ✅ `fmes.operator.allocation` calendar/list, with a "Copy to Next Week" bulk action so a stable roster is a few clicks, not a re-entry |
| Manpower shortage is visible next to the production shortfall it caused | ✅ `fmes.manpower.impact.report` (date × shift × department), shortage % and achievement % side by side |
| Tests pass | ✅ 297 tests, 0 failed, 0 errors |
| No warnings on install, with or without demo data | ✅ verified on the dev database and a fresh `--without-demo=all` database |

End-to-end on the demo plant: the demo roster has Panel Saw 01 fully staffed
today (2 of its standard 2) → the planning engine's manpower factor read
`1.0`. Rostering only one of the two for tomorrow dropped the factor to `0.5`
— and generating tomorrow's plan actually used it: the saw's line landed at
`3.75` planned hours, exactly half its normal 7.5-hour shift capacity, not
just an isolated factor calculation. An operator linked to that roster
correctly saw no machines before being rostered, and exactly the rostered
machine once added — the day's actual roster taking priority over the
permanent assignment Phase 4 shipped with, which stays as the fallback for a
plant that has not started rostering a given day yet.

**Deviations and findings**

1. **Assumption `A49` had already been used once**, for the exact placeholder
   this phase resolves (`fmes.planning.engine._get_manpower_factor` returning
   a flat `1.0` "until Phase 8"). Phase 6 added a *second*, unrelated `A49`
   (the bottleneck-suggestion threshold) without noticing the collision — a
   `grep` that should have caught it did, technically, but the two entries
   sat far enough apart in the document that the sorted listing used at the
   time still missed the duplicate visually. Renumbered the Phase 6 entry to
   `A52` (the next free id) and left the original alone, since Phase 8 is
   what actually resolves it. *Generalisable: when adding a new assumption
   id, grep for the exact string, not just eyeball a sorted list — a
   duplicate hides easily in eighty-plus rows.*
2. **Department-scoped supervisor rules, promised in `fmes_record_rules.xml`'s
   own header comment since Phase 1** ("arrive in Phase 8, once
   `res.users.fmes_department_ids` exists"), are delivered here for this
   phase's own two new models (`fmes.manpower.log`, `fmes.operator.
   allocation`) — an empty `fmes_department_ids` reads as "responsible for
   all departments," matching the field's own help text, via a genuine
   Python conditional in `domain_force` rather than a domain clause. Managers
   still need their own explicit unrestricted rule on both models, for the
   same cumulative-hierarchy reason D5.3 already established — a Plant
   Manager with no personal `fmes_department_ids` would otherwise be caught
   by the supervisor's own restrictive rule. **Not** retrofitted onto the
   department-scoped models from earlier phases (`fmes.production.entry`,
   `mrp.workcenter.productivity`, the plan/plan-line pair) — a larger,
   separate exercise, noted below rather than folded into this commit.
3. Two Odoo-18-specific view errors, both caught by the install itself rather
   than by inspection: `tracking=True` is not a valid parameter on a
   `Selection` field on a model that does not inherit `mail.thread` (removed
   — `fmes.operator.allocation` has no chatter); and `quick_add` is not a
   valid `<calendar>` attribute in Odoo 18 (removed from the roster calendar
   view).

**Commit.** `feat(manpower): add operator allocation, manpower logging and impact analysis`

---

## Phase 9 — Backlog & Carry-Forward ✅

*Completed 2026-09-07 · module version `18.0.9.0.0`*

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

**Exit criteria — all met**

| Criterion | Result |
|---|---|
| Backlog quantity and trend for the last 30 days is available without manual work | ✅ `fmes.backlog.snapshot` written nightly by `fmes.backlog.service`, pivot/graph over `snapshot_date`, ageing-bucket search filters |
| Yesterday's shortfall appears in today's plan automatically | ✅ `fmes.planning.engine._cron_generate_carry_forward_plan` — a nightly wrapper around the carry-forward `generate()` already built in Phase 3, so a supervisor no longer has to click Generate Plan for it to happen |
| Tests pass | ✅ 327 tests, 0 failed, 0 errors |
| No warnings on install, with or without demo data | ✅ verified on the dev database and a fresh `--without-demo=all` database |

End-to-end: three fresh orders (on-track, two days late, and one marked
blocked for a material reason) all produced exactly one snapshot row each on
the first run, and re-running the cron immediately after left the row count
unchanged. The blocked order's own demand came back empty from the planning
engine — genuinely excluded, not just labelled. The carry-forward cron
created tomorrow's plan on its first run and returned the *same* plan object
on a second run rather than a duplicate.

**Deviations and findings**

1. **Carry-forward itself already existed, from Phase 3.** `generate()` has
   rolled unfinished released plan lines into whatever plan it builds since
   the planning engine was first written (`_collect_carry_forward`, `source=
   'carry_forward'`) — nothing about the mechanism was new here. What Phase 9
   actually adds is the missing piece: something to call it automatically,
   every night, instead of a supervisor needing to open "Generate Plan" for
   yesterday's shortfall to reappear at all. The cron is a thin, idempotent
   wrapper (skips if an auto plan already covers tomorrow) around a mechanism
   that was already correct and already tested.
2. **`is_critical`'s two conditions in assumption A32 ("> 15 days aged, or
   an order > 7 days past deadline") are genuinely two different measures,
   not one restated twice.** Read naively they overlap (a deadline-derived
   "age" would make the tighter 7-day clause always fire first). Implemented
   as intended by tracking each production order's own first-seen snapshot
   date and measuring backlog age independently of its deadline — a large
   order sitting unstarted for weeks is flagged even while its own deadline
   is still comfortably in the future, which is the whole point of a
   *second*, distinct criterion. Only tracked for production-order-backed
   rows, which carry a stable `production_id` to look up prior nights by; a
   sale-order-line row with no manufacturing order yet has no such key, so
   its criticality is judged on lateness alone.
3. **Every derived field on the snapshot model is a plain, non-computed
   field, set once by the service at write time — deliberately, not an
   oversight.** An `@api.depends` compute reading `fields.Date.context_today
   ()` would silently rewrite a two-week-old row's own `days_delayed` every
   time anyone opened it, defeating the entire point of keeping dated
   history. Documented directly on the model, since it is the kind of
   "obviously a compute" pattern every other report in this module uses,
   made deliberately different here for a specific reason.
4. `__count` is not a real, declarable field in a pivot/graph view's XML —
   Odoo offers it as a measure automatically; declaring `<field name=
   "__count" type="measure"/>` fails view validation outright (caught on
   install, not by inspection).

**Commit.** `feat(backlog): add backlog snapshots, blocking workflow and carry-forward automation`

---

## Phase 10 — Analytics & Dashboards ✅

*Completed 2026-09-07 · module version `18.0.10.0.0`*

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

**Exit criteria — met, with one deliverable knowingly deferred (see below)**

| Criterion | Result |
|---|---|
| Every one of the ten requested management metrics is on screen | ✅ all ten tiles built: KPI row (achievement/utilisation/downtime/OEE/backlog/PM-due), production trend, downtime Pareto, department performance, shift performance, machine ranking, capacity utilisation, backlog ageing, maintenance performance, productivity trend |
| The dashboard loads in under two seconds on the seeded dataset | ✅ server-side aggregation measured at **1.83 s** against a genuinely relevant 100,000-row `fmes_production_entry` dataset (down from **6.13 s** before an aggregation-count optimisation — see Decisions) |
| Tests pass | ✅ 347 tests, 0 failed, 0 errors |
| No warnings on install, with or without demo data | ✅ verified on the dev database and a fresh `--without-demo=all` database |

End-to-end on the demo plant: an approved entry's own achievement %,
utilisation % and productivity figures matched hand-aggregations of the same
underlying report rows exactly (deliverable 7) — checked both before and
after the performance rewrite, to confirm the optimisation changed nothing
about what the numbers say, only how fast they arrive.

**Deferred, deliberately: deliverable 5 (`spreadsheet_dashboard` boards).**
A published board's content is not simple XML data — it is a raw
o-spreadsheet JSON document (a real example from Odoo's own
`spreadsheet_dashboard_sale` ran to ~78 KB: cell grids, styles, borders,
chart figures anchored by pixel coordinates, pivot definitions with
per-field-type matching). Hand-authoring one reliably, without the actual
Spreadsheet editor UI to generate it, was judged too fragile a use of the
remaining effort in an already large phase — a broken or malformed
dashboard board would be worse than no board at all. What deliverable 4
(pivot/graph views on every report model — production, utilisation,
downtime, maintenance, manpower impact, backlog) already provides, plus the
Executive Dashboard itself, covers the "ad-hoc analysis" need docs/11 section
6 describes; a genuine `spreadsheet.dashboard` board remains buildable later
by a Plant Manager directly from any of those pivot views through Odoo's own
Spreadsheet app, or by a developer with browser access to author one
properly, once real production data exists to build it against. Logged here
rather than silently dropped.

**Deviations and findings**

1. **The first version of the dashboard service missed its own performance
   target by 3x** — 6.13 s against the 100k-row dataset, not the 1.83 s it
   reads now. Root cause: `fmes.production.report` and `fmes.utilization.
   report` are SQL views (`_auto = False`); every separate query against one
   re-runs its own JOIN and GROUP BY over the full underlying table, and the
   first version queried each view once per TILE that needed it — five or six
   times over, each one redoing the same expensive join. Fixed by fetching
   each view exactly ONCE per request, at the finest grain any tile needs
   (`_fetch_production_rows` / `_fetch_utilization_rows`), and having every
   tile aggregate further from that same in-memory list in plain Python.
   Caught by literally measuring against a 100k-row dataset before calling
   the phase done, not by assuming a "sum-then-divide, one query per figure"
   design would scale — the SAME correctness discipline (D0.7) does not
   guarantee performance at volume once a view sits underneath it.
2. **`_read_group` on a Date field requires an explicit granularity suffix
   in Odoo 18** (`'date:day'`, not bare `'date'`) — omitting it raises
   `ValueError: Granularity not set on a date(time) field` immediately,
   caught on the first real call rather than by inspection.
3. **Two more numbers needed their own default targets that no earlier
   phase had set**: a utilisation target (85%) and a downtime target
   (≤ 10%), distinct from the more conservative first-year OEE target
   (`A28`, 75%) — logged as assumption `A54` rather than left as an
   unexplained constant.
4. **`fmes.utilization.report` needed one more exposed column, `ok_qty`,
   to make a multi-row OEE aggregation possible at all.** The view already
   computed it internally for its own per-row `oee_pct`/`quality` columns,
   but never selected it as a column in its own right — without it, the
   dashboard's OEE KPI would have had no correct way to re-derive quality as
   `SUM(ok_qty)/SUM(actual_qty)` (D0.7) across more than one row; the only
   alternative would have been averaging the view's own already-computed
   `oee_pct`, exactly the mistake D0.7 exists to prevent.
5. **No browser was available in this environment to visually verify the
   OWL component's actual render** (Chart.js instantiation, click-through,
   layout). Verified instead: XML template well-formedness, JS syntax
   (`node --check`), the exact OWL/QWeb patterns matched against Odoo's own
   native `graph_renderer.js` and this project's own Phase 3/4 OWL
   components line-for-line, and the full backend service end-to-end via
   `odoo shell` against real approved production data. The visual render
   itself is the one thing about this phase not independently confirmed.

**Commit.** `feat(analytics): add executive dashboard and production analytics read models`

---

## Phase 11 — Alerts & Notifications ✅

*Completed 2026-09-07 · module version `18.0.11.0.0`*

**Goal.** Requirement 10.

**Deliverables**

1. `fmes.alert.rule` and `fmes.alert` models — ✅
2. `services/alert_engine.py` — evaluates rules, applies scope and cooldown,
   raises alerts, dispatches to activity / Discuss / email — ✅
3. Cron `fmes_evaluate_alerts` (every 15 minutes) for threshold-based rules;
   `base_automation` triggers for event-based rules (breakdown, block) — ✅
4. Default rules seeded in `data/alert_rules.xml` for all seven required types
   — ✅ (nine rules: two types are each seeded as a pair of rules sharing one
   `alert_type`, which is how a single rule's one threshold+operator pair
   expresses an "or" condition — see Decisions)
5. `mail.template` per alert type, with a clean HTML layout — ✅, as one
   reusable, dynamically-styled template rather than nine near-identical
   files (see Decisions)
6. **Alert Center** — list and kanban by severity, acknowledge and resolve
   actions, unread counter in the systray — ✅
7. Escalation — a critical alert unacknowledged past its window notifies the
   Plant Manager — ✅ (assumption `A55`, 30 minutes)
8. Tests: threshold boundaries, cooldown suppression, scope filtering, recipient
   resolution, no duplicate alerts for one condition — ✅ 27 new tests

**Exit criteria — met**

| Criterion | Result |
|---|---|
| Each of the seven alert types fires correctly on a seeded trigger condition | ✅ verified per type: threshold types via direct `_eval_*` evaluation tests against real production entries / downtime events / maintenance schedules; the two event-based types (`machine_breakdown`, `material_shortage`) and the block-driven `critical_backlog` path via the actual `base.automation` records firing on a real `create()`/`write()`, not by calling the engine directly |
| No alert storm: repeated conditions respect cooldown | ✅ an alert already `new`/`acknowledged` is never re-raised regardless of cooldown timing; once resolved, a re-raise is still suppressed until `cooldown_minutes` has elapsed |
| Tests pass | ✅ 374 tests module-wide, 0 failed, 0 errors (27 new for this phase) |
| No warnings on install, with or without demo data | ✅ verified on the dev database and a fresh `--without-demo=all` database |

End-to-end via `odoo shell` against the seeded dev database: all 9 default
rules present across all 7 types, the cron active on its 15-minute interval,
all 3 `base.automation` records wired, the mail template and both UI actions
resolvable, and the Alert Center menu correctly resolving to its action.

**Deviations and findings**

1. **A real QWeb compiler bug, caught only by an actual test run, not by XML
   well-formedness checking.** The mail template's severity-coloured header
   band originally computed its background colour inline, inside a
   `t-attf-style` attribute: `background:#{{ 'dc3545' if object.severity ==
   'critical' else (...) }}`. This is syntactically valid XML and valid
   Python, but Odoo 18's `t-attf-*` attribute-interpolation compiler failed
   to compile the embedded ternary at render time
   (`ValueError: Can not compile expression: ...`) — invisible to `py_compile`
   or `xml.dom.minidom` well-formedness checks, and invisible even to a plain
   module install, since a `mail.template`'s `body_html` is only compiled the
   first time an email actually renders. It surfaced the moment a real test
   (`TestEventTriggers`) triggered a critical alert's immediate dispatch.
   Fixed by moving the ternary out of the attribute interpolation entirely,
   into a `t-set`/`t-value` (full Python expression evaluation, the
   officially supported place for this), then referencing the pre-computed
   variable from `t-attf-style` as a plain name — `{{fmes_alert_color}}` —
   which is only ever a name substitution, never a re-parsed expression.
   Logged here specifically because it demonstrates why deliverable 8's test
   suite intentionally drives the real `base.automation` → engine → dispatch
   → `mail.template.send_mail` path for at least the critical-severity
   types, rather than stopping at unit-testing the engine's own Python.
2. **Two test-fixture bugs, not engine bugs, both caught by the same real
   test run.** `fmes.maintenance.schedule`'s own `_compute_next_due_date`
   treats `interval_number=0` as falsy and substitutes `1`
   (`schedule.interval_number or 1`) — an existing, correct guard against a
   schedule with no interval configured, not a Phase 11 defect — but it
   meant a first test-helper attempt to express "due today" via
   `interval_number=0` silently produced a schedule due *tomorrow* instead.
   Fixed by having the test fixture vary `last_done_date` instead of
   `interval_number` (always `1`), which cannot hit the falsy-zero case.
   Separately, two tests asserted an exact recipient set/count from
   `group_fmes_supervisor`, which is real, shared group state — the demo
   dataset adds its own members to it, so the assertion was implicitly (and
   wrongly) assuming a demo-data-free group membership, the exact coupling
   `tests/common.py`'s own docstring says this test suite must not have.
   Fixed by asserting membership/coverage of the specific users under test
   rather than the group's total size.
3. **`docker compose exec` cannot run a second `odoo` process against the
   already-running `web` service** — it shares the same container as the
   long-running server, which already holds port 8069, so `exec ... odoo ...`
   fails with `Address already in use` even with `--no-http`. The
   `Makefile`'s own `ODOO_RUN := docker compose run --rm web odoo` already
   documents exactly this and why (`run` does not publish ports; a fresh,
   throwaway container has no conflict) — this phase's verification followed
   that pattern throughout rather than `exec`.
4. **A `noupdate="1"` data file does not pick up a fix on `-u` (upgrade).**
   The QWeb bug above (finding 1) was fixed in `data/fmes_alert_mail_
   template.xml`, but that file is `noupdate="1"` by design (so a plant that
   tunes the template keeps its own edit across upgrades) — an `-u` against
   the dev database that already had the broken record left the old, broken
   template untouched. Verification for this phase therefore used a
   dropped-and-recreated dev database for the final, authoritative test run,
   the same way a genuinely new deployment would first see the fixed data.
5. **Git Bash mangles a bare `/module_name` argument into a Windows path**
   (`/furnishing_mes` became `C:/Program Files/Git/furnishing_mes`), silently
   producing an `Invalid tag` warning and a false "0 tests" pass rather than
   an obvious failure — worth remembering for any future `--test-tags
   /furnishing_mes` invocation from this shell: prefix the command with
   `MSYS_NO_PATHCONV=1`.
6. **No browser was available in this environment** to visually verify the
   Alert Center kanban/list/systray render, matching the same documented gap
   from Phase 10's Executive Dashboard. Verified instead: XML well-formedness,
   JS syntax (`node --check`), the exact kanban `t-name="card"` and systray
   `registry.category("systray")` patterns matched against this module's own
   existing components (`fmes_live_status_views.xml`, `mrp_workcenter_views.xml`)
   and Odoo's own conventions, and the full backend chain end-to-end via
   `odoo shell` and the real test suite (including the actual
   `base.automation` firing path). The visual render itself remains the one
   thing about this phase not independently confirmed.

**Commit.** `feat(alerts): add rule-driven alert engine, notifications and alert center`

---

## Phase 12 — Reporting Suite ✅

*Completed 2026-09-07 · module version `18.0.12.0.0`*

**Goal.** Requirement 12, all ten reports.

**Deliverables**

1. QWeb PDF templates with a shared branded layout (header, plant, period,
   generated-on, page numbers) for:
   Daily Production · Machine Utilisation · Production Output Summary ·
   Downtime · Backlog · Carry Forward Order · Maintenance · Productivity ·
   Exception · Monthly Management MIS — ✅, as one shared `ir.actions.report`
   + one generic QWeb template driven by `report_type` (see Decisions), not
   ten near-identical template/action pairs, mirroring the same "one
   reusable template" choice Phase 11 made for its mail template
2. XLSX export for each, via `xlsxwriter` (already bundled with Odoo) — ✅,
   one shared writer (`fmes.report.service.write_xlsx`) reading the exact
   same data dict the PDF renders from
3. `wizards/fmes_report_wizard.py` — common parameter wizard (date range,
   department, machine, shift, product, format) — ✅
4. Scheduled delivery — `fmes.report.schedule` records driving a cron that
   emails the chosen reports to chosen recipients daily / weekly / monthly
   — ✅, four seeded schedules per assumption `A36`
5. Monthly MIS pack — a composite multi-section PDF for management — ✅,
   seven summary-only sections plus a month-on-month achievement
   comparison
6. Exception report — consolidated variance and threshold breaches for the
   period — ✅, built directly on Phase 11's own `fmes.alert` records for
   the five threshold-breach alert types (see Decisions)
7. Tests: each report renders for the demo dataset without error; figures
   reconcile with the dashboard — ✅ 26 new tests, against a small fixture
   plant rather than the demo dataset itself (matching `tests/common.py`'s
   own established "never depend on demo data" rule — see Decisions)

**Exit criteria — met**

| Criterion | Result |
|---|---|
| All ten named reports produce correct PDF and XLSX output | ✅ all ten `get_report_data` types verified against fixture data; the shared QWeb template verified via its test-mode HTML render (not a forced real PDF — see Decisions) plus one manual `odoo shell` check confirming genuine `%PDF` bytes; XLSX verified by actually closing a real `xlsxwriter` workbook and reading back its sheets |
| The daily production report can be scheduled to arrive by email each morning | ✅ seeded at 07:00 daily (assumption `A36`); the cron's own send path is tested end-to-end (attachment on a real `mail.mail`, `last_run`/`next_run` advancing correctly) |
| Tests pass | ✅ 400 tests module-wide, 0 failed, 0 errors (26 new for this phase) |
| No warnings on install, with or without demo data | ✅ verified on the dev database and a fresh `--without-demo=all` database |

**Deviations and findings**

1. **One shared report action, template and XLSX writer for all ten report
   types, not ten pairs.** `services/report_service.py`'s `get_report_data`
   returns one uniform shape — `{title, period_label, filters_label,
   summary, columns, rows}` (plus `sections` for the Monthly MIS composite)
   — for every report type; a single `ir.actions.report`
   (`action_report_fmes_generic`) and a single QWeb template render
   whichever type the wizard or a schedule asks for, and
   `fmes.report.service.write_xlsx` writes the identical dict to a
   workbook. A new report type is a new `_data_<type>` method, never a new
   template — the same reasoning Phase 11 gave for its own single mail
   template, applied here at larger scale.
2. **docs/05's 8-item Reports menu covers all ten report types, not just
   eight.** `production_output_summary` and `carry_forward_order` are not
   the direct target of their own menu item; they are reachable by
   switching the wizard's own `report_type` dropdown after opening it from
   "Daily Production" or "Backlog & Carry Forward" respectively — those
   two menu items just supply a convenient default, not an exclusive path.
   Documented here since docs/05 predates this phase's own report_type
   list and reads as if there were only eight reports.
3. **A real QWeb-report gotcha, distinct from Phase 11's, caught only by an
   actual render.** `record._fields['alert_type'].selection` — read from a
   model INSTANCE of a `related=` Selection field — is not reliably the
   plain list of tuples it looks like; Odoo returned a callable there
   instead, and `dict()`-ing it raised `TypeError: 'function' object is
   not iterable`. This is exactly the class of thing that is invisible to
   `py_compile` and to a plain install, and only surfaces the moment
   `_data_exception` actually runs — caught here, not in production,
   because the Exception Report test builds and reads a real `fmes.alert`
   row rather than stopping at an empty-data smoke test. Fixed by importing
   `ALERT_TYPES` directly from `models/fmes_alert_rule.py` (the field's
   OWN original definition, not a related copy) and building the label
   dict from that, the same "single source of truth" pattern already used
   for `REPORT_TYPES` itself.
4. **A second real bug, found by the same Exception Report test once
   folded into the Monthly MIS composite:** `fmes.maintenance.report`'s
   view has no filter excluding equipment with no `mrp.workcenter` behind
   it, so an unfiltered Maintenance Report included the `maintenance`
   module's own generic IT-asset demo data (an "HP Laptop", "Acer Laptop",
   a monitor) alongside genuine plant machinery — 6 rows where a
   machine-scoped fixture expected 1. Fixed at the report layer (not by
   touching Phase 7's already-shipped view): `_data_maintenance` now
   requires `workcenter_id != False`, matching the report's own "Equipment
   > Month" grouping, which implies a machine exists.
5. **`ir.actions.report.report_action()`'s own default silently redirects
   an admin user to a "configure your document layout" onboarding wizard**
   whenever the current company has no `external_report_layout_id` set —
   invisible until a test actually inspected the returned action dict and
   found no `report_name` key at all. Not something a Plant Manager
   clicking "Generate" should ever hit; fixed by calling `report_action(self,
   config=False)` from the wizard.
6. **Forcing a real wkhtmltopdf render inside the CLI test runner
   deadlocks or times out** (`force_report_rendering=True` under
   `--test-enable`), reproducibly, regardless of which report is being
   rendered — an environment/tooling limitation of this specific
   Docker/CLI combination, not a defect in this phase's own templates or
   data. Confirmed by hand: the exact same template, rendered via `odoo
   shell` against the live, already-running `web` service (real threaded
   HTTP serving, not the single-process test runner), produced a genuine
   27 KB `%PDF`-prefixed document in under a second, with only a benign
   `ContentNotFoundError` warning for a missing logo image. The automated
   test suite therefore verifies the exact same QWeb template and data
   pipeline through `_render_qweb_pdf`'s own **default** test-mode
   behaviour (an HTML fallback, which `test_enable` already provides
   without forcing anything) rather than a forced PDF — this still catches
   the class of bug finding 3 above demonstrates (a QWeb expression that
   only fails to compile at actual render time), without the hang. Real
   PDF generation itself was independently confirmed by hand instead,
   matching the same "no browser available, verified manually" precedent
   already established in Phase 10 and Phase 11.
7. **`tests/common.py`'s own "never depend on demo data" rule turned out
   to matter for a reason beyond drift-proofing figures:** the `maintenance`
   module's stock demo equipment (finding 4) is exactly the kind of
   pollution that rule exists to keep test assertions honest about. This
   phase's fixtures build their own small plant, same as every earlier
   phase's tests, rather than reading the demo dataset.

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
