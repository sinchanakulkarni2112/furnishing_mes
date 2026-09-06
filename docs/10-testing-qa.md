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

---

## 6. Performance Benchmarks

Established in Phase 14 with `scripts/seed_load.py`:

| Dataset | Volume |
|---|---|
| Production entries | 100,000 (≈3 years, 12 machines, 3 shifts) |
| Downtime events | 50,000 |
| Backlog snapshots | 40,000 |
| Maintenance requests | 5,000 |

| Operation | Target |
|---|---|
| Executive dashboard first paint | < 2 s |
| Pivot on `fmes.production.report`, 1 year | < 3 s |
| Daily Production Report PDF | < 5 s |
| Monthly MIS pack PDF | < 10 s |
| Plan generation, 1 week × 12 machines | < 15 s |
| Terminal action round-trip | < 500 ms |
| Nightly cron suite | < 5 min |

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
