# 16 — Administrator Guide

For whoever stands up a new Furnishing MES deployment and keeps it running:
master data setup order, user onboarding, alert tuning, and report
scheduling. Deployment/infrastructure itself is `08-deployment-operations.md`
— this document starts from a running instance.

---

## 1. Master Data Setup Order

Each step depends on the ones before it — follow this order on a fresh
deployment (Configuration menu, Plant Manager role):

| Step | Menu | Depends on | Notes |
|---|---|---|---|
| 1 | Departments | — | The top-level grouping every scoping rule and report uses |
| 2 | Shifts | — | Name, start/end time, net working hours per shift |
| 3 | Machines (`mrp.workcenter`) | Departments | Machine code, department, standard manpower; bridges automatically to an Equipment record |
| 4 | Capacity Matrix | Machines | Standard output rate per machine × product (or product category), with a `basis_hours` (per-hour/shift/day) |
| 5 | Equipment | Machines (auto-bridged) | Criticality, MTBF baseline — maintenance-facing detail |
| 6 | Loss Reasons | — | Ten categories ship seeded; add plant-specific reasons under the same categories, never a new category, so downtime analysis stays comparable |

**A plan cannot be generated correctly until step 4 is complete for every
machine that will run** — a missing capacity rate resolves to `0.0`
(deliberately visible, not silently defaulted — see `docs/03-data-model.md`),
so an incomplete matrix shows up immediately as a machine planning zero
capacity, not as a wrong number.

Import templates for shifts, machines and the capacity matrix are in
`docs/templates/` if you're loading real data in bulk rather than typing it
in by hand.

## 2. User Onboarding

### Internal users (Operator / Supervisor / Plant Manager)

1. Settings → Users → New
2. Set name, email/login, and a temporary password (or trigger Odoo's own
   password-reset email)
3. Under the "Furnishing MES" access category, assign exactly **one** group:
   Operator, Supervisor, or Plant Manager. Each tier implies everything below
   it (Plant Manager ⊃ Supervisor ⊃ Operator ⊃ internal user) — never assign
   more than one.
4. For a **Supervisor**, also set `fmes_department_ids` on their user form to
   the departments they're responsible for. Leaving it empty means "all
   departments" — correct only for a supervisor who genuinely covers the
   whole plant.
5. For an **Operator**, optionally set a permanent machine assignment
   (`fmes_allowed_workcenter_ids`) — this is the fallback used on any day
   they have no roster entry; the day's actual roster (Operator Allocation)
   always takes priority when one exists.

### Portal customers

Never create a portal `res.users` record by hand — this is what the demo
data does purely for reviewer convenience (`demo/fmes_demo_portal.xml`), and
it is explicitly not the production path.

1. Contacts → open (or create) the customer's contact
2. Action → **Grant Portal Access** (native Odoo `auth_signup`, invite-only)
3. The contact receives an email with a signup link and sets their own
   password — you never see or set it
4. Any child contact at the same company can be granted access the same way;
   portal record rules use `commercial_partner_id`, so anyone at that company
   sees the company's orders and tickets, not only their own

## 3. Alert Rule Tuning

**Alerts → Alert Rules** (Plant Manager only). Nine default rules ship
seeded, covering all seven alert types (two types use a pair of rules to
express an "or" condition on the threshold). For each rule:

| Field | What it controls |
|---|---|
| Threshold + operator | The condition that raises the alert (e.g. downtime % > 15) |
| Scope | Plant-wide, or specific departments/machines |
| Cooldown (minutes) | How long before the same condition can raise a new alert — prevents an alert storm from a condition that stays true |
| Severity | Drives the mail template's colour and the escalation timer |

A critical alert unacknowledged for 30 minutes escalates to every Plant
Manager automatically — this window is not currently configurable per rule
(a fixed constant; see the known-limitations register in
`docs/17-handover-checklist.md` if this needs to become configurable).

**Tuning approach:** start from the seeded defaults, run for a week or two
against real data, then adjust thresholds with input from supervisors —
tightening a threshold that fires constantly and is ignored is worse than
leaving it looser and trusted.

## 4. Report Schedules

**Configuration → Report Schedules** (Plant Manager only). Four schedules
ship seeded (assumption `A36`) at placeholder cadences/recipients — set real
recipients before go-live, or they email nobody useful. To add a new one:
pick a report type, cadence (daily/weekly/monthly), recipients, and format
(PDF/Excel). The schedule's own cron sends it; no manual trigger is needed
once configured. See `docs/06-build-plan.md` Phase 12 for the full list of
ten report types.
