# -*- coding: utf-8 -*-
"""Manpower impact analysis (Requirement 8.5).

Grain: date x shift x department. Puts the two figures a Plant Manager wants
side by side — manpower shortage and production achievement — for the same
slot, so the correlation is something to look at in a pivot/graph rather than
a claim to take on faith. Deliberately not a computed statistical correlation
coefficient: at this grain a handful of rows per department per month would
make one arithmetically valid, but not a meaningful one.

A FULL OUTER JOIN of two independently-aggregated sides, the same shape as
`fmes.utilization.report` (Phase 6): a shift can have a manpower log with no
approved production yet, or approved production with no manpower logged
against it, and neither side should silently drop the other.
"""

from odoo import fields, models, tools


class FmesManpowerImpactReport(models.Model):
    _name = 'fmes.manpower.impact.report'
    _description = 'Manpower Impact Analysis'
    _auto = False
    _order = 'date desc, shift_id, department_id'
    _rec_name = 'department_id'

    date = fields.Date(readonly=True)
    shift_id = fields.Many2one('fmes.shift', string='Shift', readonly=True)
    department_id = fields.Many2one(
        'hr.department', string='Department', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)

    std_manpower = fields.Float(string='Standard Manpower', readonly=True)
    actual_manpower = fields.Float(string='Actual Manpower', readonly=True)
    shortage = fields.Float(readonly=True)
    shortage_pct = fields.Float(
        string='Shortage %', readonly=True, aggregator=None)
    absent_count = fields.Integer(readonly=True)
    overtime_hours = fields.Float(readonly=True)

    planned_qty = fields.Float(
        readonly=True, digits='Product Unit of Measure')
    actual_qty = fields.Float(
        readonly=True, digits='Product Unit of Measure')
    has_planned_qty = fields.Boolean(
        readonly=True,
        help="False when no approved production exists for this slot — "
             "lets the UI show '—' rather than a misleading 0% achievement.")
    achievement_pct = fields.Float(
        string='Achievement %', readonly=True, aggregator=None,
        help="0 when has_planned_qty is False.")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW %s AS (
                WITH manpower_agg AS (
                    SELECT
                        date, shift_id, department_id,
                        SUM(std_manpower) AS std_manpower,
                        SUM(actual_manpower) AS actual_manpower,
                        SUM(absent_count) AS absent_count,
                        SUM(overtime_hours) AS overtime_hours
                    FROM fmes_manpower_log
                    GROUP BY date, shift_id, department_id
                ),
                production_agg AS (
                    SELECT
                        e.date, e.shift_id, wc.department_id,
                        SUM(e.planned_qty) AS planned_qty,
                        SUM(e.actual_qty) AS actual_qty
                    FROM fmes_production_entry e
                    JOIN mrp_workcenter wc ON wc.id = e.workcenter_id
                    WHERE e.state = 'approved'
                      AND wc.department_id IS NOT NULL
                    GROUP BY e.date, e.shift_id, wc.department_id
                ),
                combined AS (
                    SELECT
                        COALESCE(m.date, p.date) AS date,
                        COALESCE(m.shift_id, p.shift_id) AS shift_id,
                        COALESCE(m.department_id, p.department_id)
                            AS department_id,
                        COALESCE(m.std_manpower, 0) AS std_manpower,
                        COALESCE(m.actual_manpower, 0) AS actual_manpower,
                        COALESCE(m.absent_count, 0) AS absent_count,
                        COALESCE(m.overtime_hours, 0) AS overtime_hours,
                        COALESCE(p.planned_qty, 0) AS planned_qty,
                        COALESCE(p.actual_qty, 0) AS actual_qty
                    FROM manpower_agg m
                    FULL OUTER JOIN production_agg p
                        ON m.date = p.date
                       AND m.shift_id = p.shift_id
                       AND m.department_id = p.department_id
                )
                SELECT
                    ROW_NUMBER() OVER (
                        ORDER BY c.date, c.shift_id, c.department_id) AS id,
                    c.date, c.shift_id, c.department_id, dept.company_id,
                    c.std_manpower, c.actual_manpower,
                    (c.std_manpower - c.actual_manpower) AS shortage,
                    CASE WHEN c.std_manpower > 0
                         THEN (c.std_manpower - c.actual_manpower)
                              / c.std_manpower * 100.0
                         ELSE 0 END AS shortage_pct,
                    c.absent_count, c.overtime_hours,
                    c.planned_qty, c.actual_qty,
                    (c.planned_qty > 0) AS has_planned_qty,
                    CASE WHEN c.planned_qty > 0
                         THEN c.actual_qty / c.planned_qty * 100.0
                         ELSE 0 END AS achievement_pct
                FROM combined c
                JOIN hr_department dept ON dept.id = c.department_id
            )
        """ % self._table)
