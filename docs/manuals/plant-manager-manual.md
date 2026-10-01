# Plant Manager Manual

For the Plant Manager role — full control over the system. You have every
Supervisor right, plus master data ownership, alert rule authoring, report
scheduling, and the executive dashboard.

---

## 1. Executive Dashboard

**Analytics → Executive Dashboard** is your daily starting point: one screen
with the ten management metrics —

- Achievement %, Utilisation %, Downtime %, OEE, Backlog quantity, Open
  maintenance (KPI row)
- Production trend, Utilisation trend, Downtime trend (trend charts)
- Department performance, Shift performance (comparison charts)
- Downtime loss-reason Pareto
- Capacity utilisation gauge, Backlog ageing, Maintenance performance

Every tile is clickable through to the underlying records, and the date-range
and department filters at the top apply plant-wide. Supervisors see the same
dashboard scoped to their own departments only; yours is unscoped.

Note on load time: the dashboard is optimised to fetch each underlying report
once per load, but at very high data volumes (~100k+ production entries) it
can run to around 5 seconds rather than the original 2-second target — a
known, documented, structural limitation of the SQL-view aggregation
underneath it (see `docs/17-handover-checklist.md`'s limitations register),
not something a setting fixes.

## 2. Master Data Ownership

Set these up in this order — later ones depend on earlier ones:

1. **Configuration → Departments**
2. **Configuration → Shifts** — the three-shift pattern (or your own)
3. **Configuration → Machines** — each machine's department, standard
   manpower, and bridge to its Equipment record
4. **Configuration → Capacity Matrix** — standard output rate per
   machine/product (or product category); a plan cannot be generated
   correctly until this is filled in for every machine that will run
5. **Configuration → Equipment** — maintenance-relevant detail (criticality,
   MTBF baseline); bridged automatically to/from the matching machine
6. **Configuration → Loss Reasons** — the ten downtime categories ship
   seeded; add plant-specific reasons under the same categories if needed

You are the only role that can edit the Capacity Matrix or delete master
records.

## 3. User Onboarding

**Internal users** (Operator / Supervisor / Plant Manager): Settings → Users
→ New, then assign exactly one of the three Furnishing MES groups
(Operator / Supervisor / Plant Manager) under the "Furnishing MES" access
category — each tier automatically includes everything below it, so assign
only the highest tier a person needs. For a Supervisor, also set their
`fmes_department_ids` (on their user form) to the departments they're
responsible for — leave it empty only if they genuinely cover the whole
plant.

**Portal customers**: never create a portal login by hand. Open the
customer's contact under Contacts, and use **Action → Grant Portal Access**
— Odoo's own native invitation flow (`auth_signup`, invite-only). The contact
receives an email with a signup link; you never see or set their password.
See `docs/16-administrator-guide.md` for the full walkthrough.

## 4. Alert Rules

**Alerts → Alert Rules**: nine default rules covering all seven alert types
ship pre-configured (some types use a pair of rules to express an "or"
condition on the threshold). To tune a rule: open it, adjust the threshold,
operator, scope (plant-wide or specific departments/machines), and cooldown
period. A tighter threshold means more alerts; a longer cooldown means fewer
repeats for a condition that stays true. Review thresholds with input from
supervisors during go-live — the seeded defaults are reasonable starting
points, not measured against your actual plant yet.

## 5. Report Schedules

**Configuration → Report Schedules**: four schedules ship seeded (daily,
weekly, monthly cadences to a placeholder recipient list). Edit each to set
real recipients, or add a new schedule for any of the ten report types —
daily / weekly / monthly cadence, chosen recipients, PDF or Excel. The
schedule's own cron sends it automatically; no manual trigger needed once
configured.

## 6. Monthly MIS

**Reports → Monthly MIS** produces the composite management pack: seven
summary sections plus a month-on-month achievement comparison, as one PDF.
This is the report to send up rather than the ten individual ones, for a
monthly review.

## 7. Things Only You Can Do

- Edit the Capacity Matrix or delete master data records
- Create, edit, or delete Alert Rules
- Create or edit Report Schedules
- Unlock an approved production entry or downtime event for correction
- Grant portal access to a new customer contact
- Assign the Plant Manager or Supervisor group to a user

Everything else — approvals, planning, rosters, maintenance, backlog — you
can also do directly; see `supervisor-manual.md` for those day-to-day
mechanics, since your access is a strict superset of a Supervisor's.
