# -*- coding: utf-8 -*-
"""Downtime analysis read model.

Requirement 6.3/6.4: loss-reason analysis and the downtime report. A SQL view
rather than Python aggregation (ADR-004) — the customer wants trend analysis
over history, and letting PostgreSQL do the grouping is what keeps that fast
as records accumulate.

Grain: date x shift x machine x loss reason, per docs/11-reporting-analytics.md
section 2.2.

Only **approved** events are counted (the same rule Phase 4 established for
production entries, D4.1): a downtime figure a supervisor has not signed off
is not something this report should represent as fact. Odoo's own native OEE
computation is not gated this way — it reads every completed event regardless
of review state — which is a deliberate, documented difference: OEE is a
real-time operational number, this report is a reviewed one.
"""

from odoo import fields, models, tools


class FmesDowntimeReport(models.Model):
    _name = 'fmes.downtime.report'
    _description = 'Downtime Analysis'
    _auto = False
    _order = 'date desc, downtime_hours desc'
    _rec_name = 'loss_id'

    date = fields.Date(readonly=True)
    shift_id = fields.Many2one('fmes.shift', string='Shift', readonly=True)
    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Machine', readonly=True)
    department_id = fields.Many2one(
        'hr.department', string='Department', readonly=True)
    loss_id = fields.Many2one(
        'mrp.workcenter.productivity.loss', string='Loss Reason',
        readonly=True)
    fmes_category = fields.Selection(
        [('maintenance', 'Maintenance'),
         ('power_failure', 'Power Failure'),
         ('material_shortage', 'Material Shortage'),
         ('material_handling', 'Material Handling Delay'),
         ('operator_absence', 'Operator Absence'),
         ('manpower_rescheduling', 'Manpower Rescheduling'),
         ('operator_inefficiency', 'Operator Inefficiency'),
         ('unscheduled_stoppage', 'Unscheduled Stoppage'),
         ('changeover', 'Changeover / Setup'),
         ('other', 'Other')],
        string='Loss Category', readonly=True)
    loss_type = fields.Selection(
        [('availability', 'Availability'), ('performance', 'Performance'),
         ('quality', 'Quality'), ('productive', 'Productive')],
        string='Effectiveness', readonly=True)
    is_planned = fields.Boolean(string='Planned Stoppage', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)

    downtime_hours = fields.Float(string='Downtime Hours', readonly=True)
    event_count = fields.Integer(string='Events', readonly=True)
    avg_event_duration = fields.Float(
        string='Avg Event (hours)', readonly=True)
    pct_of_available = fields.Float(
        string='% of Shift Capacity', readonly=True,
        help="Downtime hours as a share of the shift's net available hours "
             "for this machine.")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW %s AS (
                SELECT
                    MIN(p.id) AS id,
                    p.date_start::date AS date,
                    p.fmes_shift_id AS shift_id,
                    p.workcenter_id AS workcenter_id,
                    wc.department_id AS department_id,
                    p.loss_id AS loss_id,
                    p.fmes_category AS fmes_category,
                    p.loss_type AS loss_type,
                    loss.fmes_is_planned AS is_planned,
                    p.company_id AS company_id,
                    SUM(p.duration) / 60.0 AS downtime_hours,
                    COUNT(*) AS event_count,
                    AVG(p.duration) / 60.0 AS avg_event_duration,
                    CASE WHEN sh.net_hours > 0
                         THEN SUM(p.duration) / 60.0 / sh.net_hours * 100.0
                         ELSE 0.0
                    END AS pct_of_available
                FROM mrp_workcenter_productivity p
                JOIN mrp_workcenter wc ON wc.id = p.workcenter_id
                LEFT JOIN mrp_workcenter_productivity_loss loss
                       ON loss.id = p.loss_id
                LEFT JOIN fmes_shift sh ON sh.id = p.fmes_shift_id
                WHERE p.date_end IS NOT NULL
                  AND p.fmes_state = 'approved'
                  AND p.loss_type != 'productive'
                GROUP BY
                    p.date_start::date, p.fmes_shift_id, p.workcenter_id,
                    wc.department_id, p.loss_id, p.fmes_category,
                    p.loss_type, loss.fmes_is_planned, p.company_id,
                    sh.net_hours
            )
        """ % self._table)
