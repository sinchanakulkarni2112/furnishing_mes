# -*- coding: utf-8 -*-
"""Machine utilisation and OEE analysis read model.

Requirement 5.1/5.2/5.3 and Requirement 3.6. A SQL view (ADR-004), grain
date x shift x machine, per docs/11-reporting-analytics.md section 2.3.

Built from two things Phases 4 and 5 already produce correctly:

- `fmes.production.entry` (approved only, D0.6/D4.1) for planned/actual/ok
  quantity, run hours and the standard-output figure already sized per row
  by the capacity matrix.
- `mrp.workcenter.productivity` (approved, completed, non-productive only,
  D5's own rule) for the planned/unplanned downtime split, via the loss
  reason's `fmes_is_planned` flag.

A FULL OUTER JOIN, not a one-sided one: a shift can have approved production
with no downtime at all (a clean run), or downtime with no production logged
against that same date/shift/machine, and neither side should silently drop
the other. `fmes_shift_id` is a related field off `fmes_entry_id` (Phase 5),
so a downtime event logged with no linked entry has no shift to place it in —
this shift-grained report necessarily excludes it, the same way it excludes
any row it cannot assign a shift to; it still counts toward the machine's
overall MTBF/MTTR in Phase 7's maintenance reporting.

Aggregation follows the project's own rule (D0.7): sum first, then divide.
`std_output_qty` on the entry is already `rate x run_hours` per row, so
`SUM(actual_qty) / SUM(std_output_qty)` is the same generalisation of
"performance" the metric doc gives for a single row, extended correctly to a
period that may span several products at different rates.
"""

from odoo import fields, models, tools


class FmesUtilizationReport(models.Model):
    _name = 'fmes.utilization.report'
    _description = 'Machine Utilisation & OEE Analysis'
    _auto = False
    _order = 'date desc, workcenter_id'
    _rec_name = 'workcenter_id'

    date = fields.Date(readonly=True)
    shift_id = fields.Many2one('fmes.shift', string='Shift', readonly=True)
    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Machine', readonly=True)
    department_id = fields.Many2one(
        'hr.department', string='Department', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)

    available_hours = fields.Float(string='Available Hours', readonly=True)
    run_hours = fields.Float(string='Run Hours', readonly=True)
    planned_downtime_hours = fields.Float(
        string='Planned Downtime', readonly=True)
    unplanned_downtime_hours = fields.Float(
        string='Unplanned Downtime', readonly=True)
    idle_hours = fields.Float(
        string='Idle Hours', readonly=True,
        help="Available hours not accounted for by run time or any coded "
             "downtime — time nothing at all was logged against.")

    std_output_qty = fields.Float(
        string='Standard Output', readonly=True,
        digits='Product Unit of Measure')
    actual_qty = fields.Float(
        string='Actual Output', readonly=True,
        digits='Product Unit of Measure')
    ok_qty = fields.Float(
        string='Good Output', readonly=True,
        digits='Product Unit of Measure',
        help="Exposed so a multi-row OEE aggregation (Phase 10's Executive "
             "Dashboard) can re-derive quality as SUM(ok_qty)/SUM(actual_qty) "
             "— D0.7 — rather than averaging this view's own per-row oee_pct.")

    utilization_pct = fields.Float(
        string='Utilisation %', readonly=True,
        help="Run hours over available hours (Requirement 5.1).")
    availability = fields.Float(
        string='Availability', readonly=True,
        help="OEE factor 1: available hours less unplanned downtime, over "
             "available hours. Planned stoppages are not counted against it.")
    performance = fields.Float(
        string='Performance', readonly=True,
        help="OEE factor 2: actual output over standard output for the "
             "hours actually run.")
    quality = fields.Float(
        string='Quality', readonly=True,
        help="OEE factor 3: good output over total output.")
    oee_pct = fields.Float(
        string='OEE %', readonly=True,
        help="Availability x Performance x Quality x 100. Cross-checked "
             "against Odoo's native mrp.workcenter.oee.")
    efficiency_pct = fields.Float(
        string='Efficiency %', readonly=True,
        help="Actual output over standard output — standard vs actual, "
             "Requirement 5.2. Same figure as Performance, expressed as a "
             "percentage for a reader comparing it to the per-entry field.")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW %s AS (
                WITH entry_agg AS (
                    SELECT
                        date, shift_id, workcenter_id,
                        SUM(actual_qty) AS actual_qty,
                        SUM(ok_qty) AS ok_qty,
                        SUM(run_hours) AS run_hours,
                        SUM(std_output_qty) AS std_output_qty
                    FROM fmes_production_entry
                    WHERE state = 'approved'
                    GROUP BY date, shift_id, workcenter_id
                ),
                downtime_agg AS (
                    SELECT
                        p.date_start::date AS date,
                        p.fmes_shift_id AS shift_id,
                        p.workcenter_id AS workcenter_id,
                        SUM(CASE WHEN loss.fmes_is_planned
                                 THEN p.duration ELSE 0 END) / 60.0
                            AS planned_downtime_hours,
                        SUM(CASE WHEN NOT COALESCE(loss.fmes_is_planned, FALSE)
                                 THEN p.duration ELSE 0 END) / 60.0
                            AS unplanned_downtime_hours
                    FROM mrp_workcenter_productivity p
                    LEFT JOIN mrp_workcenter_productivity_loss loss
                           ON loss.id = p.loss_id
                    WHERE p.fmes_state = 'approved'
                      AND p.date_end IS NOT NULL
                      AND p.loss_type != 'productive'
                      AND p.fmes_shift_id IS NOT NULL
                    GROUP BY p.date_start::date, p.fmes_shift_id,
                             p.workcenter_id
                ),
                combined AS (
                    SELECT
                        COALESCE(e.date, d.date) AS date,
                        COALESCE(e.shift_id, d.shift_id) AS shift_id,
                        COALESCE(e.workcenter_id, d.workcenter_id)
                            AS workcenter_id,
                        COALESCE(e.actual_qty, 0) AS actual_qty,
                        COALESCE(e.ok_qty, 0) AS ok_qty,
                        COALESCE(e.run_hours, 0) AS run_hours,
                        COALESCE(e.std_output_qty, 0) AS std_output_qty,
                        COALESCE(d.planned_downtime_hours, 0)
                            AS planned_downtime_hours,
                        COALESCE(d.unplanned_downtime_hours, 0)
                            AS unplanned_downtime_hours
                    FROM entry_agg e
                    FULL OUTER JOIN downtime_agg d
                        ON e.date = d.date
                       AND e.shift_id = d.shift_id
                       AND e.workcenter_id = d.workcenter_id
                )
                SELECT
                    ROW_NUMBER() OVER (
                        ORDER BY c.date, c.shift_id, c.workcenter_id) AS id,
                    c.date, c.shift_id, c.workcenter_id,
                    wc.department_id, wc.company_id,
                    sh.net_hours AS available_hours,
                    c.run_hours,
                    c.planned_downtime_hours,
                    c.unplanned_downtime_hours,
                    GREATEST(
                        sh.net_hours - c.run_hours
                        - c.planned_downtime_hours
                        - c.unplanned_downtime_hours,
                        0) AS idle_hours,
                    c.std_output_qty,
                    c.actual_qty,
                    c.ok_qty,
                    CASE WHEN sh.net_hours > 0
                         THEN c.run_hours / sh.net_hours * 100.0
                         ELSE 0 END AS utilization_pct,
                    CASE WHEN sh.net_hours > 0
                         THEN (sh.net_hours - c.unplanned_downtime_hours)
                              / sh.net_hours
                         ELSE 0 END AS availability,
                    CASE WHEN c.std_output_qty > 0
                         THEN c.actual_qty / c.std_output_qty
                         ELSE 0 END AS performance,
                    CASE WHEN c.actual_qty > 0
                         THEN c.ok_qty / c.actual_qty
                         ELSE 0 END AS quality,
                    CASE WHEN sh.net_hours > 0 AND c.std_output_qty > 0
                              AND c.actual_qty > 0
                         THEN
                            ((sh.net_hours - c.unplanned_downtime_hours)
                                / sh.net_hours)
                            * (c.actual_qty / c.std_output_qty)
                            * (c.ok_qty / c.actual_qty)
                            * 100.0
                         ELSE 0 END AS oee_pct,
                    CASE WHEN c.std_output_qty > 0
                         THEN c.actual_qty / c.std_output_qty * 100.0
                         ELSE 0 END AS efficiency_pct
                FROM combined c
                JOIN mrp_workcenter wc ON wc.id = c.workcenter_id
                LEFT JOIN fmes_shift sh ON sh.id = c.shift_id
            )
        """ % self._table)
