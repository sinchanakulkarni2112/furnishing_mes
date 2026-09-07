# Supervisor Manual

For shift/department supervisors. You have every Operator right, plus
approval, scheduling, and department-scoped reporting rights. Everything
below is reachable from the main **Furnishing MES** menu once logged in
through the normal Odoo web interface (not the shop-floor terminal).

---

## 1. Daily Cycle

A typical day, roughly in order:

1. **Review yesterday's approval queues** (Production → Approval Queue,
   Downtime → Approval Queue) — approve or reject entries your operators
   submitted.
2. **Check the Live Status board** (Production → Live Status) for machines
   currently down or idle.
3. **Check Alerts** (Alerts → Alert Center) for anything raised against your
   departments overnight.
4. **Adjust today's operator roster** if someone is absent (Manpower →
   Operator Roster).
5. **Release tomorrow's plan** if not already auto-generated (Planning →
   Generate Plan / Scheduling Board).

## 2. Approving Production & Downtime

- **Production → Approval Queue**: a list of `submitted` entries. Select one
  or many and use the bulk **Approve** / **Reject** action. A rejected entry
  returns to the operator as `draft` so they can fix and resubmit it.
- **Downtime → Approval Queue**: the same pattern for downtime events.
  Rejecting a downtime event returns it to the operator, and — if it had
  triggered a maintenance escalation — that request stays open regardless
  (the escalation is not undone by a rejection).
- Once approved, neither you nor the operator can edit the record. Only a
  Plant Manager can unlock an approved entry.

You only see entries for machines/departments you are responsible for
(`fmes_department_ids` on your user, set by the Plant Manager). Leaving this
empty makes you responsible for *all* departments — check with your Plant
Manager which applies to you.

## 3. Production Planning

- **Planning → Generate Plan** opens the plan-generator wizard: choose a date
  range, plan type, departments, and demand source (open manufacturing
  orders, optionally sales orders), then run it. The engine produces a
  `draft` plan with a capacity-utilisation preview — no plan line ever
  exceeds a machine's capacity for its shift.
- **Planning → Scheduling Board** shows machines on one axis and
  dates/shifts on the other, colour-coded by load; drag a line to reassign
  it or click to open it directly.
- Review the draft, then **Confirm** and **Release** it. Releasing creates or
  updates the linked manufacturing work orders' schedule dates.
- **Planning → Carry Forward** shows yesterday's unfinished plan lines that
  rolled into today automatically overnight — no action needed unless you
  want to review what carried over.

## 4. Operator Allocation (Roster)

**Manpower → Operator Roster**: assign operators to machines by date and
shift, calendar or list view. Use **Copy to Next Week** to repeat a stable
roster instead of re-entering it. The roster is what actually scopes an
operator's terminal (today's roster takes priority over their permanent
machine assignment) and feeds the planning engine's manpower factor — an
under-staffed machine's planned capacity is derated automatically, so the
roster is not just an HR record, it changes tomorrow's plan.

**Manpower → Manpower Impact Report** shows shortage % next to achievement %
by department and shift, so you can see whether a bad day was a staffing
problem.

## 5. Maintenance

- **Maintenance → Schedules**: preventive-maintenance schedules for your
  equipment. The system raises a request automatically ahead of each due
  date — you don't create these by hand, but you can review and adjust the
  schedule (interval, lead time).
- **Maintenance → Requests**: both preventive and breakdown requests. A
  breakdown request created from a downtime escalation carries the machine,
  the downtime event, and the lost hours already filled in.
- **Maintenance → KPIs**: MTBF, MTTR, PM-compliance and cost, by equipment and
  month.

## 6. Backlog

**Backlog → Overview / Blocked / Delayed**: read-only views of open order
status. If an order genuinely cannot proceed (material shortage, a customer
hold), mark it **Blocked** with a reason from the order form — this removes
it from the planning engine's demand until you clear the block.

## 7. Alerts

**Alerts → Alert Center**: acknowledge and resolve alerts raised against your
departments (threshold breaches, machine breakdowns, critical backlog). An
unacknowledged critical alert escalates to the Plant Manager automatically
after 30 minutes, so don't leave one sitting.

**Alerts → Alert Rules** is read-only for you — only a Plant Manager can
create or edit a rule.

## 8. Reports

**Reports** menu: run any of the ten standard reports (Daily Production,
Machine Utilisation, Downtime, Backlog, Maintenance, Productivity, Exception,
etc.) for your own departments, as PDF or Excel, through the report wizard.
You cannot create scheduled report deliveries — that's a Plant Manager task.

## 9. Things You Cannot Do

- Change the capacity matrix, machine master data, or alert rule definitions
- Create or edit report schedules
- Unlock an approved production entry or downtime event
- See or manage other departments' data (unless your `fmes_department_ids`
  is empty, meaning you're responsible for all of them)

These are Plant Manager tasks — see `plant-manager-manual.md`.
