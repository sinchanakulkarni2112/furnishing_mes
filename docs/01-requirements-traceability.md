# 01 — Requirements Traceability Matrix

Every line in `customer_requirements.txt` is mapped to a design decision, an
implementation artefact and a delivery phase. This is the contract used to verify
completeness at handover.

**Legend for "Approach":**
`REUSE` = native Odoo 18 Community capability ·
`EXTEND` = Odoo model extended by `furnishing_mes` ·
`NEW` = model/logic built from scratch

---

## R1 — Production Planning Automation

| # | Requirement | Approach | Artefact | Phase |
|---|---|---|---|---|
| 1.1 | Automatically generate production plans | NEW | `fmes.planning.engine`, `fmes.plan.generator` wizard | 3 |
| 1.2 | Planning based on machine capacity matrix | NEW | `fmes.capacity.matrix` | 2, 3 |
| 1.3 | Consider available manpower | NEW | `fmes.manpower.log`, `std_manpower` on capacity matrix | 3, 8 |
| 1.4 | Consider machine availability | EXTEND | `resource.calendar` + maintenance windows + downtime history | 3 |
| 1.5 | Machine-wise production schedules | NEW | `fmes.production.plan.line` grouped by `workcenter_id` | 3 |
| 1.6 | Shift-wise production plans | NEW | `fmes.shift` + `shift_id` on every plan line | 2, 3 |
| 1.7 | Reduce Excel dependency | NEW | Scheduling Board (OWL) + XLSX import/export | 3, 4 |

## R2 — Daily Production Plan & Output Tracking

| # | Requirement | Approach | Artefact | Phase |
|---|---|---|---|---|
| 2.1 | Capture daily production targets | NEW | `fmes.production.entry.planned_qty` | 4 |
| 2.2 | Record actual production output | NEW | `fmes.production.entry.actual_qty` + Shop-Floor Terminal | 4 |
| 2.3 | Compare planned vs actual | NEW | `achievement_pct` computed + variance views | 4 |
| 2.4 | Date-wise production reports | NEW | `fmes.production.report` SQL view, QWeb + XLSX | 4, 12 |
| 2.5 | Shift-wise production reports | NEW | Same, grouped by `shift_id` | 4, 12 |
| 2.6 | Track production performance daily | NEW | Daily Production Report + dashboard KPI | 10, 12 |

## R3 — Production Monitoring

| # | Requirement | Approach | Artefact | Phase |
|---|---|---|---|---|
| 3.1 | Monitor machine-wise | REUSE + NEW | `mrp.workcenter` kanban + live status board | 4, 6 |
| 3.2 | Monitor department-wise | EXTEND | `department_id` (`hr.department`) on `mrp.workcenter` | 2, 6 |
| 3.3 | Centralised production database | REUSE | PostgreSQL 15, single Odoo database | 1 ✅ |
| 3.4 | Historical production records | NEW | `fmes.production.entry`, locked after approval | 4 |
| 3.5 | Real-time production status | NEW | OWL live board over `mrp.workorder` state | 4, 10 |
| 3.6 | Machine utilisation & productivity | REUSE + NEW | `mrp.workcenter.oee` + `fmes.utilization.report` | 6 |

## R4 — Backlog and Carry-Forward Order Management

| # | Requirement | Approach | Artefact | Phase |
|---|---|---|---|---|
| 4.1 | Track pending production orders | NEW | `fmes.backlog.snapshot` (status `pending`) | 9 |
| 4.2 | Track blocked orders | NEW | `block_reason` + status `blocked` | 9 |
| 4.3 | Carry-forward order reports | NEW | Carry-forward cron + `source='carry_forward'` plan lines | 9, 12 |
| 4.4 | Identify delayed orders | NEW | `days_delayed` computed against `date_deadline` | 9 |
| 4.5 | Monitor order completion status | REUSE | `mrp.production.state` + progress % | 9 |
| 4.6 | Backlog quantity and trends | NEW | Nightly snapshots to time-series graph view | 9, 10 |

## R5 — Machine Utilisation Monitoring

| # | Requirement | Approach | Artefact | Phase |
|---|---|---|---|---|
| 5.1 | Machine-wise utilisation % | NEW | `fmes.utilization.report` (run hours over available hours) | 6 |
| 5.2 | Standard vs actual output | NEW | Capacity-matrix standard rate vs `actual_qty` | 6 |
| 5.3 | Monitor machine efficiency | REUSE | `mrp.workcenter.oee`, `time_efficiency` | 6 |
| 5.4 | Identify under-utilised machines | NEW | Threshold filter + dashboard tile | 6, 10 |
| 5.5 | Analyse production bottlenecks | NEW | `is_bottleneck` flag + load-vs-capacity analysis | 6 |

## R6 — Downtime Management

| # | Requirement | Approach | Artefact | Phase |
|---|---|---|---|---|
| 6.1 | Capture downtime reasons digitally | EXTEND | `mrp.workcenter.productivity.loss` + `fmes_category` | 5 |
| 6.2 | Measure downtime hours | REUSE | `mrp.workcenter.productivity.duration` | 5 |
| 6.3 | Analyse loss reasons | NEW | `fmes.downtime.report` pivot and Pareto view | 5, 10 |
| 6.4 | Generate downtime reports | NEW | QWeb PDF + XLSX Downtime Report | 5, 12 |

**Reason taxonomy** — seeded as `mrp.workcenter.productivity.loss` records, all
drawn from the customer's existing process:

`maintenance` · `power_failure` · `material_shortage` · `material_handling` ·
`operator_absence` · `manpower_rescheduling` · `operator_inefficiency` ·
`unscheduled_stoppage` · `changeover` · `other`

## R7 — Machine Maintenance Management

| # | Requirement | Approach | Artefact | Phase |
|---|---|---|---|---|
| 7.1 | Machine master management | REUSE + EXTEND | `maintenance.equipment` to `mrp.workcenter` bridge | 2, 7 |
| 7.2 | Preventive maintenance scheduling | REUSE + NEW | `maintenance.request` recurrence + `fmes.maintenance.schedule` | 7 |
| 7.3 | Breakdown maintenance tracking | REUSE | `maintenance_type='corrective'` linked to downtime log | 7 |
| 7.4 | Maintenance history records | REUSE | `maintenance.request` history on equipment | 7 |
| 7.5 | Maintenance alerts and reminders | NEW | `fmes.alert.rule` type `maintenance_due` + activities | 11 |
| 7.6 | Machine health monitoring | REUSE + NEW | Native MTBF / MTTR + composite health score | 7 |
| 7.7 | Maintenance KPI reports | NEW | `fmes.maintenance.report` + QWeb/XLSX | 7, 12 |

## R8 — Production Resource Management

| # | Requirement | Approach | Artefact | Phase |
|---|---|---|---|---|
| 8.1 | Track manpower deployment | NEW | `fmes.operator.allocation` | 8 |
| 8.2 | Standard vs actual manpower | NEW | `fmes.manpower.log` std/actual fields | 8 |
| 8.3 | Track operator shortage | NEW | `shortage` computed + `absent_count` | 8 |
| 8.4 | Monitor manpower utilisation | NEW | `utilization_pct` on manpower log | 8 |
| 8.5 | Manpower impact on production | NEW | Correlation view: shortage vs achievement % | 8, 10 |

## R9 — Production Analytics & Dashboards

All ten requested metrics land in Phase 10 on the Executive Dashboard (an OWL
client action) backed by SQL-view report models.

| Metric | Source |
|---|---|
| Production achievement % | `fmes.production.report` |
| Machine utilisation % | `fmes.utilization.report` |
| Downtime % | `fmes.downtime.report` |
| Productivity analysis | output divided by manpower-hours |
| Department performance | grouped by `department_id` |
| Shift performance | grouped by `shift_id` |
| Production trends | time series over production entries |
| Capacity utilisation | planned load divided by matrix capacity |
| Order backlog analysis | `fmes.backlog.snapshot` |
| Maintenance performance | `fmes.maintenance.report` |

## R10 — Alerts & Notifications

Phase 11. A single rule engine, `fmes.alert.rule`, with these seeded types:
`machine_breakdown` · `excess_downtime` · `target_not_achieved` ·
`maintenance_due` · `material_shortage` · `critical_backlog` · `delayed_order`.

Channels: in-app activity, Odoo Discuss message, and email via `mail.template`.

## R11 — ERP 10.8 Integration

**Deferred by customer decision.** The design seam is documented in
[`09-erp-integration-roadmap.md`](09-erp-integration-roadmap.md). Phase 2 seeds
mock Sales Orders, Work Orders, Item Master, BOM and Customer Master inside Odoo
so every downstream phase can be built and demonstrated without ERP access.

## R12 — Reporting Requirements

Phase 12 delivers all ten reports as QWeb PDF plus XLSX, each with a scheduled
email option:

| Report | Backing model |
|---|---|
| Daily Production Report | `fmes.production.report` |
| Machine Utilisation Report | `fmes.utilization.report` |
| Production Output Summary | `fmes.production.report` |
| Downtime Report | `fmes.downtime.report` |
| Backlog Report | `fmes.backlog.snapshot` |
| Carry Forward Order Report | `fmes.production.plan.line` (carry-forward) |
| Maintenance Report | `fmes.maintenance.report` |
| Productivity Report | output divided by manpower-hours |
| Exception Reports | alert and variance thresholds |
| Monthly Management MIS | composite pack of the above |

---

## Note on the Customer's Solution Approach

The requirements document proposes *"Odoo Manufacturing"* as the solution option.
This project implements exactly that, as a **custom module on Odoo 18 Community**
rather than a stock installation, because several capabilities the customer asked
for — the Shop Floor terminal, Gantt-style scheduling, and the work-center to
equipment bridge — are Enterprise-only and are therefore built in-house. See
[`13-odoo-edition-constraints.md`](13-odoo-edition-constraints.md).
