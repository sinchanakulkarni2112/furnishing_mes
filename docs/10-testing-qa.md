# 10 — Testing & QA Strategy

Tests are written **in the phase that introduces the code**, not deferred to
Phase 14. Phase 14 is a hardening sweep, not the first time anything is tested.

---

## 1. Test Pyramid

```
            ┌──────────────────────┐
            │   Manual / UAT       │  Per phase demo, persona walkthroughs
            ├──────────────────────┤
            │   HttpCase / Tours   │  Terminal, dashboard, portal flows
            ├──────────────────────┤
            │   Integration        │  Workflows across models, crons
            ├──────────────────────┤
            │   Unit               │  Computes, constraints, services   ← most
            └──────────────────────┘
```

The bulk of the value is in unit tests over the service layer — the planning
engine, utilisation maths, backlog classification and alert evaluation are where
the real logic lives, and they are pure functions of their inputs by design
(principle A3 in the architecture doc).

---

## 2. Framework

Odoo's own test framework, run inside the container.

| Base class | For |
|---|---|
| `TransactionCase` | Models, computes, constraints, services. Rolled back per test |
| `SavepointCase` / `TransactionCase` with `setUpClass` | Shared expensive fixtures |
| `HttpCase` | Controllers, portal routes, OWL tours |
| `Form` | Onchange behaviour exactly as the UI would trigger it |

```bash
make test                                              # everything
docker compose exec web odoo -d furnishing_mes -u furnishing_mes \
  --test-enable --test-tags /furnishing_mes:TestPlanningEngine \
  --log-level=test --stop-after-init
```

Tag convention: `@tagged('post_install', '-at_install', 'fmes')`, plus a phase
tag such as `fmes_phase3`, so a phase's tests can be run in isolation.

---

## 3. Fixtures

`tests/common.py` provides `FmesTestCase`, a base class that builds a small,
deterministic plant:

- 1 company, 2 departments
- 3 work centers with linked equipment
- 3 shifts (A 06:00–14:00, B 14:00–22:00, C 22:00–06:00)
- 4 products with BOMs
- A capacity matrix covering every machine/product pair used in tests
- 5 open manufacturing orders with staggered deadlines

Fixed dates are used throughout (`2026-01-05` onwards) so no test depends on
"today" and results are stable in CI. Where a test genuinely needs "now", it
freezes time rather than reading the clock.

---

## 4. What Each Phase Must Test

| Phase | Required tests |
|---|---|
| 1 | Module installs; the four groups exist with correct `implied_ids`; every model in the manifest has an ACL row |
| 2 | Capacity resolution order (product → category → default); overlapping validity rejected; work center ↔ equipment bridge stays consistent both ways; sequences generate |
| 3 | Capacity maths per shift; no line exceeds capacity; changeover minutes deducted; carry-forward demand included ahead of new orders; deterministic output for the fixture; manual override survives regeneration |
| 4 | `achievement_pct` and `variance_qty` maths incl. zero-target guard; uniqueness constraint; approved entries immutable except for manager; operator sees only allocated machines; importer round-trip and error reporting; reversal of an import batch |
| 5 | Downtime duration maths; category rollup; auto-escalation creates exactly one maintenance request; downtime hours propagate to the production entry; Odoo's native OEE stays consistent |
| 6 | Utilisation % against a known fixture shift; efficiency vs standard output; under-utilised threshold boundaries; bottleneck ranking order |
| 7 | Schedule recurrence and `next_due_date` recomputation; lead-time generation window; no duplicate open PM request; MTBF/MTTR sanity; health score bounds 0–100 |
| 8 | Shortage and utilisation maths; allocation uniqueness per employee/shift/day; capacity derating when manpower is short |
| 9 | Snapshot idempotency (running twice for one date produces one row set); classification boundaries (pending/delayed/at-risk); **carry-forward quantity conservation** — total demand is neither lost nor duplicated |
| 10 | Every dashboard KPI equals the same figure computed from the underlying records; SQL views return correct aggregates; date-range and department filters apply |
| 11 | Threshold boundary conditions (just under, exactly at, just over); cooldown suppresses duplicates; scope filtering; recipient resolution; escalation fires |
| 12 | Every report renders without error for the demo dataset; report figures reconcile with the dashboard; XLSX opens and has the expected sheets and headers |
| 13 | Cross-customer access denied; portal user cannot reach `/web`; ticket ownership enforced; progress figures exclude internal data |
| 14 | The full security suite (below); performance benchmarks; restore drill |

---

## 5. Security Test Suite — `tests/test_security.py`

The ten checks from [`04-security-model.md`](04-security-model.md) section 6,
implemented as assertions that the expected `AccessError` is raised or the
recordset is empty. This suite is a **release gate**: a failure blocks the phase,
it is not triaged as a bug to fix later.

Every test uses `with self.assertRaises(AccessError):` against a user actually
created in that group — never `sudo()`, which would bypass the very thing under
test.

**Results (2026-09-07).** T1-T7 and T10 are real `TransactionCase`/`HttpCase`
tests (17 total, all passing). T8 (database manager blocked by `list_db =
False`) and T9 (no published PostgreSQL port) are **verified by configuration
review, not a runtime test**: this dev container deliberately runs with
`list_db = True` (docs/04 section 5.1's own table — the first-run wizard
needs it), so a test asserting `list_db = False` behaviour would either be
vacuous or would have to fight the project's own intentional dev settings.
T8 is confirmed by reading `config/odoo.conf`'s production template
(`list_db = False`); T9 by reading `docker-compose.yml`'s `db` service, which
publishes no host port at all — both facts, not runtime assertions, and both
re-verified any time either file changes.

The audit (deliverable 1) found five real gaps beyond what `test_security.py`
itself tests — see `docs/06-build-plan.md`'s own Phase 14 "Deviations and
findings" for the full account. The most serious: the write rules for
`fmes.production.entry` and `mrp.workcenter.productivity` had no workcenter
scope at all, so any Operator could edit any OTHER operator's draft entry on
any machine — closed with the same OR-with-`create_uid` pattern the read
rules already used correctly.

---

## 6. Performance Benchmarks

Established in Phase 14 with `scripts/seed_load.py` — a bulk-SQL generator,
not the ORM (six-figure `create()` calls would take on the order of hours;
see the script's own docstring). Idempotent and marker-tagged so it can be
re-run any time without accumulating duplicate rows, and is never loaded
outside an explicit, deliberate run of the script itself.

| Dataset | Target volume | Actually generated (2026-09-07) |
|---|---|---|
| Production entries | 100,000 | 99,954 |
| Downtime events | 50,000 | 50,006 (includes the loss-reason join row) |
| Backlog snapshots | 40,000 | 40,000 |
| Maintenance requests | 5,000 | 5,005 |

| Operation | Target | Measured (2026-09-07) | Result |
|---|---|---|---|
| Executive dashboard first paint | < 2 s | **5.0 s** | ❌ over target — root-caused, not fixed this phase; see below |
| Pivot on `fmes.production.report`, 1 year | < 3 s | 0.85 s (19,764 rows) | ✅ |
| Daily Production Report (data) | < 5 s | 0.65 s | ✅ |
| Monthly MIS pack (data only, not PDF) | < 10 s | 3.3 s | ✅ |
| Plan generation, 1 week × 12 machines | < 15 s | not re-measured this phase (Phase 3's own benchmark stands) | — |
| Terminal action round-trip | < 500 ms | not re-measured this phase | — |
| Nightly cron suite | < 5 min | not re-measured this phase | — |

**The dashboard finding, in full.** `EXPLAIN ANALYZE` on the query
`dashboard_service.py`'s own `_fetch_production_rows` issues shows the
`fmes.production.report` VIEW performs a `HashAggregate` at its own full
`date × shift × workcenter × department × product × category × company`
grain across the entire 99,954-row underlying table — 263-449 ms — BEFORE
the outer date-range filter or the dashboard's own coarser regroup can apply
at all; Postgres does not push the predicate through the view boundary here.
This happens TWICE per dashboard load (current period, then the previous
period for the trend comparison), and the same shape recurs for `fmes.
utilization.report`. Base-table indexes were confirmed comprehensive first
(`\d fmes_production_entry` — every foreign key, `date`, and `state` all
already indexed) — this is not a missing-index problem; the query performs
a full aggregation regardless of what is indexed.

The pre-planned escalation path (`docs/11-reporting-analytics.md` section 2:
*"if latency becomes a problem, `fmes.production.report` is promoted to a
materialised view refreshed by cron — Phase 14 escalation path"*) is the
architecturally correct fix, and is **deliberately not implemented this
phase**: a materialised view trades this problem for staleness, and a large
number of tests across Phases 4-13 depend on the view being live within the
same transaction (`env.flush_all()` then an immediate read — D6.1's own
established pattern, used pervasively). Converting now would need every one
of those tests audited for whether it needs an explicit `REFRESH`, which is
a correctness-risk-bearing exercise far outside a performance-tuning pass
this late in the project. A lower-risk alternative is recorded as the
recommended next step instead: have `dashboard_service.py`'s own fetch
methods read `fmes.production.entry` / `mrp.workcenter.productivity`
directly, since the dashboard already re-aggregates at its own coarser grain
and the view's finer one is wasted work for this specific caller — not
attempted this phase given the risk of quietly duplicating aggregation logic
in an already-shipped, KPI-correctness-critical component under time
pressure.

**Coverage (deliverable 3), measured for real with `coverage.py`** (not in
the base Odoo image — installed per-run with `pip install --break-system-
packages coverage`, `COVERAGE_FILE` pointed at a writable path, and
`MSYS_NO_PATHCONV=1` needed for that env var to survive Git Bash on
Windows): **87%** combined across `models/` and `services/` (2,751
statements, 894 branches), comfortably over the 80% target. `services/`
alone: **≈88.6%**. The one service noticeably under the bar is `alert_
engine.py` at 66% — its untested lines are mostly the individual `_eval_
<type>` methods' less-common branches and the notification-dispatch paths
that depend on real email delivery timing, not exercised by the automated
suite (Phase 11's own D11.6 already documents why real send timing is
checked by hand, not by an automated test).

**Backup and restore drill (deliverable 9), timed for real** against the
195,000-row seeded database: `pg_dump -Fc` — **8 s**, 15.2 MB. `pg_restore`
into a fresh, empty database — **44 s**. Row counts matched exactly
(`fmes_production_entry`: 99,954 in both). A fresh Odoo process (`--stop-
after-init`) booted against the restored database with no errors, confirming
the restore reproduces a database Odoo itself considers valid, not merely
one `pg_restore` reports success on.

Measured with `EXPLAIN ANALYZE` on the underlying queries, not just wall-clock,
so a regression can be attributed to a specific query plan.

---

## 7. Manual / UAT Checklist

Run at the end of each phase, and in full before handover. Each persona walks
their real daily routine:

**Operator** — log in, open the terminal, pick a machine, start a work order,
record output, log a downtime with a reason, submit the shift.

**Supervisor** — review the approval queue, approve a shift, reject one with a
comment, escalate a downtime to maintenance, plan tomorrow's roster, release
tomorrow's plan.

**Plant Manager** — open the dashboard, drill from a KPI to the records,
generate a week's plan, tune an alert threshold, run the monthly MIS, add a
machine to the capacity matrix.

**Customer** — log into the portal, view an order's progress, raise a ticket,
reply to a response, and confirm no other customer's data is reachable.

---

## 8. Definition of Done — QA View

A phase is not done until:

- [ ] All new models have unit tests for computes and constraints
- [ ] All new services have tests for the happy path and at least two edge cases
- [ ] All new ACLs and record rules have a security test
- [ ] `make test` passes with zero failures and zero errors
- [ ] Module install and upgrade produce no warnings at `--log-level=warn`
- [ ] The persona walkthrough for the affected role passes manually
- [ ] No regression in the previous phases' tests

---

## 9. Known Testing Constraints

| Constraint | Handling |
|---|---|
| OWL component tests are heavier than model tests | Cover component *logic* in JS unit tests where practical; cover the *flow* with one HttpCase tour per screen rather than exhaustive UI tests |
| Cron behaviour depends on dates | Crons are thin wrappers that call a service method with explicit dates; the service is what is tested |
| Demo data drift | Tests build their own fixtures via `FmesTestCase` and never rely on `demo/` records |
| Timezone effects on shift C (overnight) | Explicit tests for the 22:00–06:00 wrap, in a non-UTC company timezone |
