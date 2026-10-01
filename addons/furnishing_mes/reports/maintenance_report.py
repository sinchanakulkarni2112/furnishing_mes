# -*- coding: utf-8 -*-
"""Maintenance KPI read model (Requirement 7.7).

Grain: month x equipment, per docs/11-reporting-analytics.md section 2.4.

Everything computable from stored columns — request/PM/breakdown counts,
PM-compliance, downtime hours, cost, overdue count — is a genuine SQL
aggregate. MTBF and MTTR are deliberately NOT part of the view's own SELECT:
they are native, non-stored Python computes on `maintenance.equipment`
(`maintenance.mixin._compute_maintenance_request`), so a raw SQL view has no
column to read them from. Reusing them as-is — "not recomputed by us"
(docs/11 section 1) — means reading `equipment_id.mtbf` / `.mttr` directly in
an ordinary (non-view) compute layered on top of this model instead, which is
exactly what `_compute_equipment_reliability` below does.

A request's `close_date` doubles as its "done" flag here, the same way
Phase 5/6 use it: native `maintenance.request.write()` sets `close_date`
exactly when `stage_id.done` becomes true and clears it otherwise, so
`close_date IS NOT NULL` is a reliable, join-free proxy for done.
"""

from odoo import api, fields, models, tools


class FmesMaintenanceReport(models.Model):
    _name = 'fmes.maintenance.report'
    _description = 'Maintenance KPI Report'
    _auto = False
    _order = 'month desc, equipment_id'
    _rec_name = 'equipment_id'

    month = fields.Date(readonly=True)
    equipment_id = fields.Many2one(
        'maintenance.equipment', string='Equipment', readonly=True)
    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Machine', readonly=True)
    department_id = fields.Many2one(
        'hr.department', string='Department', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)

    request_count = fields.Integer(readonly=True)
    preventive_count = fields.Integer(readonly=True)
    corrective_count = fields.Integer(readonly=True)
    pm_due_count = fields.Integer(
        readonly=True,
        help="Preventive requests due in this month with a due date to "
             "judge against.")
    has_pm_due = fields.Boolean(
        readonly=True,
        help="False when no PM was due this month for this machine — lets "
             "the UI show '—' rather than a misleading 0% compliance.")
    pm_compliance_pct = fields.Float(
        string='PM Compliance %', readonly=True,
        help="Preventive requests closed on or before their due date, over "
             "preventive requests due. 0 when has_pm_due is False.")
    overdue_count = fields.Integer(
        string='Currently Overdue', readonly=True,
        help="Of the PMs due in this month, how many are still open and "
             "past their due date as of today.")
    downtime_hours = fields.Float(readonly=True)
    cost = fields.Float(readonly=True)

    mtbf = fields.Integer(
        compute='_compute_equipment_reliability', string='MTBF (days)')
    mttr = fields.Integer(
        compute='_compute_equipment_reliability', string='MTTR (days)')

    @api.depends('equipment_id.mtbf', 'equipment_id.mttr')
    def _compute_equipment_reliability(self):
        for row in self:
            row.mtbf = row.equipment_id.mtbf
            row.mttr = row.equipment_id.mttr

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW %s AS (
                WITH base AS (
                    SELECT
                        r.id,
                        date_trunc(
                            'month',
                            COALESCE(r.fmes_due_date, r.request_date)
                        )::date AS month,
                        r.equipment_id,
                        r.maintenance_type,
                        r.fmes_due_date,
                        r.close_date,
                        r.fmes_cost,
                        r.fmes_productivity_id
                    FROM maintenance_request r
                    WHERE r.equipment_id IS NOT NULL
                      AND r.archive = FALSE
                ),
                agg AS (
                    SELECT
                        b.month,
                        b.equipment_id,
                        COUNT(*) AS request_count,
                        SUM(CASE WHEN b.maintenance_type = 'preventive'
                                 THEN 1 ELSE 0 END) AS preventive_count,
                        SUM(CASE WHEN b.maintenance_type = 'corrective'
                                 THEN 1 ELSE 0 END) AS corrective_count,
                        SUM(CASE WHEN b.maintenance_type = 'preventive'
                                      AND b.fmes_due_date IS NOT NULL
                                 THEN 1 ELSE 0 END) AS pm_due_count,
                        SUM(CASE WHEN b.maintenance_type = 'preventive'
                                      AND b.fmes_due_date IS NOT NULL
                                      AND b.close_date IS NOT NULL
                                      AND b.close_date <= b.fmes_due_date
                                 THEN 1 ELSE 0 END) AS pm_on_time_count,
                        SUM(CASE WHEN b.maintenance_type = 'preventive'
                                      AND b.fmes_due_date IS NOT NULL
                                      AND b.close_date IS NULL
                                      AND b.fmes_due_date < CURRENT_DATE
                                 THEN 1 ELSE 0 END) AS overdue_count,
                        SUM(COALESCE(b.fmes_cost, 0)) AS cost,
                        SUM(COALESCE(p.duration, 0)) / 60.0 AS downtime_hours
                    FROM base b
                    LEFT JOIN mrp_workcenter_productivity p
                           ON p.id = b.fmes_productivity_id
                    GROUP BY b.month, b.equipment_id
                )
                SELECT
                    ROW_NUMBER() OVER (
                        ORDER BY a.month, a.equipment_id) AS id,
                    a.month, a.equipment_id,
                    eq.workcenter_id, wc.department_id, eq.company_id,
                    a.request_count, a.preventive_count, a.corrective_count,
                    a.pm_due_count, (a.pm_due_count > 0) AS has_pm_due,
                    CASE WHEN a.pm_due_count > 0
                         THEN a.pm_on_time_count::float
                              / a.pm_due_count * 100.0
                         ELSE 0 END AS pm_compliance_pct,
                    a.overdue_count, a.downtime_hours, a.cost
                FROM agg a
                JOIN maintenance_equipment eq ON eq.id = a.equipment_id
                LEFT JOIN mrp_workcenter wc ON wc.id = eq.workcenter_id
            )
        """ % self._table)
