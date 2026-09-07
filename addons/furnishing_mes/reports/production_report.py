# -*- coding: utf-8 -*-
"""Production output read model (Requirement 9).

Grain: date x shift x workcenter x product, per
docs/11-reporting-analytics.md section 2.1. The most fundamental report in
the module — achievement %, the first tile on the Executive Dashboard — and
deliberately the last of the four `_auto = False` read models to be built:
every other report phase (utilisation, downtime, maintenance) already needed
its own view before this one did, and nothing about production entries
themselves changes once this exists, so building it here rather than in
Phase 4 cost nothing and avoided a report nobody was consuming yet.

Only **approved** entries count (D4.1, the same rule every other report in
this module follows): a figure a supervisor has not signed off is not
something a report should represent as fact.

`manpower_hours` exists purely to make the Productivity metric
(`ok_qty / (actual_manpower x shift_hours)`, docs/11 section 1) aggregate
correctly across a date range that spans more than one shift: `actual_manpower
x shift.net_hours` is computed per row, at this grain, where shift_id is
still singular — summing THAT and then dividing SUM(ok_qty) by it is the
correct generalisation (D0.7), where averaging a per-row productivity figure
would not be.
"""

from odoo import fields, models, tools


class FmesProductionReport(models.Model):
    _name = 'fmes.production.report'
    _description = 'Production Output Analysis'
    _auto = False
    _order = 'date desc, workcenter_id'
    _rec_name = 'workcenter_id'

    date = fields.Date(readonly=True)
    week = fields.Date(readonly=True, help="Monday of the entry's week.")
    month = fields.Date(readonly=True, help="First day of the entry's month.")
    year = fields.Date(readonly=True, help="First day of the entry's year.")
    shift_id = fields.Many2one('fmes.shift', string='Shift', readonly=True)
    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Machine', readonly=True)
    department_id = fields.Many2one(
        'hr.department', string='Department', readonly=True)
    product_id = fields.Many2one(
        'product.product', string='Product', readonly=True)
    product_category_id = fields.Many2one(
        'product.category', string='Product Category', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)

    planned_qty = fields.Float(
        readonly=True, digits='Product Unit of Measure')
    actual_qty = fields.Float(
        readonly=True, digits='Product Unit of Measure')
    rejected_qty = fields.Float(
        readonly=True, digits='Product Unit of Measure')
    ok_qty = fields.Float(readonly=True, digits='Product Unit of Measure')
    variance_qty = fields.Float(
        readonly=True, digits='Product Unit of Measure',
        help="Actual minus planned.")
    has_planned_qty = fields.Boolean(
        readonly=True,
        help="False when no target was set for this slot — lets the UI "
             "show '—' rather than a misleading 0% achievement.")
    achievement_pct = fields.Float(
        string='Achievement %', readonly=True, aggregator=None)
    efficiency_pct = fields.Float(
        string='Efficiency %', readonly=True, aggregator=None)

    run_hours = fields.Float(readonly=True)
    downtime_hours = fields.Float(readonly=True)
    available_hours = fields.Float(readonly=True)
    std_manpower = fields.Float(readonly=True)
    actual_manpower = fields.Float(readonly=True)
    manpower_hours = fields.Float(
        readonly=True,
        help="Actual manpower x the shift's net hours, summed. The "
             "denominator for a correctly-aggregated Productivity figure.")
    entry_count = fields.Integer(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW %s AS (
                SELECT
                    ROW_NUMBER() OVER (
                        ORDER BY e.date, e.shift_id, e.workcenter_id,
                                 e.product_id) AS id,
                    e.date,
                    date_trunc('week', e.date)::date AS week,
                    date_trunc('month', e.date)::date AS month,
                    date_trunc('year', e.date)::date AS year,
                    e.shift_id, e.workcenter_id, wc.department_id,
                    e.product_id, pt.categ_id AS product_category_id,
                    e.company_id,
                    SUM(e.planned_qty) AS planned_qty,
                    SUM(e.actual_qty) AS actual_qty,
                    SUM(e.rejected_qty) AS rejected_qty,
                    SUM(e.ok_qty) AS ok_qty,
                    SUM(e.actual_qty - e.planned_qty) AS variance_qty,
                    (SUM(e.planned_qty) > 0) AS has_planned_qty,
                    CASE WHEN SUM(e.planned_qty) > 0
                         THEN SUM(e.actual_qty) / SUM(e.planned_qty) * 100.0
                         ELSE 0 END AS achievement_pct,
                    CASE WHEN SUM(e.std_output_qty) > 0
                         THEN SUM(e.actual_qty) / SUM(e.std_output_qty)
                              * 100.0
                         ELSE 0 END AS efficiency_pct,
                    SUM(e.run_hours) AS run_hours,
                    SUM(e.downtime_hours) AS downtime_hours,
                    SUM(e.available_hours) AS available_hours,
                    SUM(e.std_manpower) AS std_manpower,
                    SUM(e.actual_manpower) AS actual_manpower,
                    SUM(e.actual_manpower * COALESCE(sh.net_hours, 0))
                        AS manpower_hours,
                    COUNT(*) AS entry_count
                FROM fmes_production_entry e
                JOIN mrp_workcenter wc ON wc.id = e.workcenter_id
                JOIN product_product pp ON pp.id = e.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN fmes_shift sh ON sh.id = e.shift_id
                WHERE e.state = 'approved'
                GROUP BY
                    e.date, e.shift_id, e.workcenter_id, wc.department_id,
                    e.product_id, pt.categ_id, e.company_id
            )
        """ % self._table)
