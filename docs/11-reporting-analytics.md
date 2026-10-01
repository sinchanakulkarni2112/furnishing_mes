# 11 — Reporting & Analytics Specification

Requirements 9 and 12. Every metric definition here is authoritative — the
dashboard, the PDF and the XLSX must all compute a given figure the same way, and
Phase 12 tests that they reconcile.

---

## 1. Metric Definitions

Ambiguity in a KPI definition is how two reports end up disagreeing. These are fixed.

| Metric | Formula | Notes |
|---|---|---|
| **Achievement %** | `SUM(actual_qty) / SUM(planned_qty) × 100` | Aggregate then divide — never average the per-row percentages, which would weight a 10-unit line equally with a 1,000-unit line. Zero planned yields null, not zero |
| **Available hours** | `shift.net_hours × machine-shift count` | Net of scheduled breaks |
| **Run hours** | `SUM(productivity.duration)` where `loss_type = 'productive'` | From the native productivity log |
| **Downtime hours** | `SUM(productivity.duration)` where `loss_type != 'productive'` | Split into planned and unplanned by `fmes_is_planned` |
| **Utilisation %** | `run_hours / available_hours × 100` | Requirement 5.1 |
| **Downtime %** | `downtime_hours / available_hours × 100` | Requirement 9 |
| **Availability** | `(available_hours − unplanned_downtime) / available_hours` | OEE factor 1. Planned stoppages excluded |
| **Performance** | `actual_qty / (run_hours × std_output_per_hour)` | OEE factor 2, standard rate from the capacity matrix |
| **Quality** | `ok_qty / actual_qty` | OEE factor 3 |
| **OEE %** | `Availability × Performance × Quality × 100` | Cross-checked against Odoo's native `mrp.workcenter.oee` |
| **Efficiency %** | `actual_qty / std_output_qty × 100` | Standard vs actual output, Requirement 5.2 |
| **Productivity** | `ok_qty / (actual_manpower × shift_hours)` | Units per manpower-hour |
| **Manpower utilisation %** | `actual_manpower / std_manpower × 100` | |
| **Capacity utilisation %** | `planned_hours / available_hours × 100` | Planning-side, distinct from execution-side utilisation |
| **Backlog quantity** | `SUM(pending_qty)` where status is not `completed` | From the nightly snapshot |
| **Days delayed** | `snapshot_date − date_deadline`, floored at 0 | |
| **PM compliance %** | `PMs completed on time / PMs due × 100` | |
| **MTBF / MTTR** | Odoo native, on `maintenance.equipment` | Not recomputed by us |

**Rounding.** Percentages to one decimal, hours to two, quantities to the
product's UoM precision. Rounding happens at presentation, never in intermediate
aggregation.

**Null handling.** A period with no planned quantity shows "—", not "0 %".
Distinguishing "no target was set" from "we achieved nothing" matters to the
people reading these reports.

---

## 2. Read Models (SQL Views)

Four `_auto = False` models, defined in `reports/`. Each is created with
`tools.drop_view_if_exists` then `CREATE VIEW` in `init()`.

### 2.1 `fmes.production.report`

Grain: one row per `date × shift × workcenter × product`.

Dimensions: `date`, `shift_id`, `workcenter_id`, `department_id`, `product_id`,
`product_category_id`, `company_id`, plus derived `week`, `month`, `year`.

Measures: `planned_qty`, `actual_qty`, `rejected_qty`, `ok_qty`, `variance_qty`,
`achievement_pct`, `efficiency_pct`, `run_hours`, `downtime_hours`,
`available_hours`, `std_manpower`, `actual_manpower`, `entry_count`.

Source: `fmes_production_entry` where `state = 'approved'`. Draft and submitted
data never reaches a report — this is what makes the reports trustworthy.

### 2.2 `fmes.downtime.report`

Grain: `date × shift × workcenter × loss reason`.

Dimensions: `date`, `shift_id`, `workcenter_id`, `department_id`, `loss_id`,
`fmes_category`, `loss_type`, `is_planned`.

Measures: `downtime_hours`, `event_count`, `avg_event_duration`,
`pct_of_available` (window function over the machine-shift total).

### 2.3 `fmes.utilization.report`

Grain: `date × shift × workcenter`.

Measures: `available_hours`, `run_hours`, `planned_downtime_hours`,
`unplanned_downtime_hours`, `idle_hours`, `utilization_pct`, `availability`,
`performance`, `quality`, `oee_pct`, `std_output_qty`, `actual_qty`.

Built by joining production entries and the productivity log per machine-shift.

### 2.4 `fmes.maintenance.report`

Grain: `month × equipment`.

Measures: `request_count`, `preventive_count`, `corrective_count`,
`pm_compliance_pct`, `mtbf`, `mttr`, `downtime_hours`, `cost`, `overdue_count`.

**Indexes.** Each view's underlying tables carry the indexes listed in
[`03-data-model.md`](03-data-model.md) section 13. Views themselves are not
indexed; if latency becomes a problem, `fmes.production.report` is promoted to a
materialised view refreshed by cron (Phase 14 escalation path).

---

## 3. Dashboards (Phase 10)

### 3.1 Executive Dashboard

Layout in [`05-ui-ux-design.md`](05-ui-ux-design.md) section 3.3. Content:

| Section | Content | Requirement |
|---|---|---|
| KPI row | Achievement %, Utilisation %, Downtime %, OEE %, Backlog qty, PMs due — each with trend vs the previous period and its target | 9.1–9.3 |
| Production trend | Daily planned vs actual, line chart | 9.7 |
| Downtime Pareto | Loss hours by reason, descending, with a cumulative % line | 6.3 |
| Department performance | Achievement % by department, bar | 9.5 |
| Shift performance | Achievement % and utilisation by shift, grouped bar | 9.6 |
| Machine utilisation | Ranked horizontal bar, under-utilised machines highlighted | 5.1, 5.4 |
| Capacity utilisation | Planned load vs capacity gauge, per department | 9.8 |
| Backlog ageing | Stacked bar by 0–3 / 4–7 / 8–15 / 15+ day buckets | 9.9 |
| Maintenance performance | MTBF, MTTR, PM compliance, open breakdowns | 9.10 |
| Productivity | Units per manpower-hour, trend | 9.4 |

Global filters: period (today / this week / this month / this quarter / custom),
department, and — for the manager variant — company.

Every tile drills through to the underlying records with the dashboard's filters
carried into the action's domain.

### 3.2 Live Production Status

A separate, auto-refreshing board for wall displays: machine kanban coloured by
current state (running / idle / blocked / maintenance), showing current work
order, shift target, produced so far and achievement bar. Refresh every 30 s.

### 3.3 Supervisor Dashboard

The executive dashboard pre-filtered to the supervisor's departments, with two
extra tiles: pending approvals and today's manpower shortage.

---

## 4. The Ten Reports (Phase 12)

Each ships as QWeb PDF **and** XLSX, driven by the common parameter wizard
(date range, department, machine, shift, product, format).

| # | Report | Grouping | Key columns |
|---|---|---|---|
| 1 | **Daily Production Report** | Date → Shift → Machine | Product, planned, actual, rejected, achievement %, run hrs, downtime hrs, manpower |
| 2 | **Machine Utilisation Report** | Machine → Date | Available / run / down / idle hours, utilisation %, OEE and its three factors |
| 3 | **Production Output Summary** | Period → Department → Product | Total planned, actual, ok, rejected, achievement %, trend vs previous period |
| 4 | **Downtime Report** | Category → Reason → Machine | Hours, events, average duration, % of available, top-5 Pareto band |
| 5 | **Backlog Report** | Status → Department → Order | Customer, product, ordered, produced, pending, deadline, days delayed, block reason |
| 6 | **Carry Forward Order Report** | Date → Machine | Origin plan line, carried quantity, reason, new scheduled date, cumulative carry-forward |
| 7 | **Maintenance Report** | Equipment → Month | PM vs breakdown counts, PM compliance %, MTBF, MTTR, downtime hours, cost |
| 8 | **Productivity Report** | Department → Shift | Output, manpower deployed, units per manpower-hour, std vs actual manpower, shortage impact |
| 9 | **Exception Report** | Exception type | Every threshold breach in the period: below-target shifts, excess downtime, overdue PM, critical backlog, delayed orders — one consolidated action list |
| 10 | **Monthly Management MIS** | Composite | Executive summary page, then a condensed section from each report above, with month-on-month comparison |

**Shared layout.** One `fmes_report_layout` QWeb template: logo, title, plant,
period, filters applied, generated-on, page x of y. Filters are printed on the
page so a report is never mistaken for the unfiltered whole.

**XLSX.** Generated with `xlsxwriter` (bundled with Odoo). One sheet per section,
frozen header row, auto-filter, number formats matching the rounding rules above,
and a *Parameters* sheet recording exactly what was requested.

---

## 5. Scheduled Delivery

`fmes.report.schedule`:

| Field | Purpose |
|---|---|
| `report_type` | Which of the ten |
| `frequency` | `daily` / `weekly` / `monthly` |
| `run_time` | Hour of day |
| `day_of_week` / `day_of_month` | For weekly / monthly |
| `department_ids`, `workcenter_ids` | Scope |
| `recipient_ids` | `res.partner` |
| `format` | `pdf` / `xlsx` / `both` |
| `period_offset` | Which period to report on — "yesterday", "last week", "last month" |
| `active`, `last_run`, `next_run` | |

A single cron `fmes_send_scheduled_reports` runs hourly, picks up due schedules,
renders and emails them via `mail.template`. Failures raise an activity for the
Plant Manager rather than failing silently — an MIS report that quietly stops
arriving is worse than one that errors loudly.

Typical configuration at go-live:
- Daily Production Report — every morning 07:00 to plant manager and supervisors
- Downtime Report — weekly Monday to plant manager and maintenance
- Backlog Report — daily 18:00 to planning
- Monthly MIS — 1st of the month to management

---

## 6. Ad-hoc Analysis

Beyond the fixed reports, every read model is exposed with pivot and graph views
so a manager can answer a question nobody anticipated without a developer. Saved
filters and favourites let those become team-shared views.

`spreadsheet_dashboard` (available in Odoo 18 Community) provides management
self-service spreadsheets over the same data, for the cases where the answer
needs a spreadsheet rather than a chart.
