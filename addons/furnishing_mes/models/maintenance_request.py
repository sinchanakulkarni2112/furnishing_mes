# -*- coding: utf-8 -*-
"""`maintenance.request` extension (Requirement 7.3).

Adds the work-center link, the origin schedule for a preventive request, the
downtime event a breakdown request escalated from, cost, and a filled
checklist. Odoo's own stage/kanban/calendar/recurrence machinery is left
untouched — extending the native model (ADR-001) is what keeps native MTBF/
MTTR reading real data instead of a second, disconnected history.
"""

from odoo import api, fields, models


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Machine', index=True,
        help="Set automatically from the equipment, when the equipment is "
             "bridged to a machine (Requirement 7.1).")
    fmes_schedule_id = fields.Many2one(
        'fmes.maintenance.schedule', string='Preventive Schedule',
        readonly=True, copy=False, index=True,
        help="Set when this request was raised by the preventive scheduler. "
             "Blank for a breakdown request.")
    fmes_due_date = fields.Date(
        string='Due Date', readonly=True, copy=False,
        help="Snapshot of the schedule's due date at the moment this "
             "request was generated. The schedule's own next_due_date moves "
             "on as soon as this cycle completes, so PM-compliance "
             "reporting needs its own frozen copy to judge 'on time' "
             "against, the same way an approved production entry freezes "
             "its own figures instead of trusting a value that keeps moving.")
    fmes_productivity_id = fields.Many2one(
        'mrp.workcenter.productivity', string='Downtime Event', readonly=True,
        copy=False, index=True,
        help="The downtime event that escalated into this request, for a "
             "breakdown raised from the terminal (Requirement 6, "
             "deliverable 4).")
    fmes_downtime_hours = fields.Float(
        compute='_compute_fmes_downtime_hours', string='Downtime Hours',
        aggregator=None,
        help="Production time lost to this breakdown, read live from the "
             "linked downtime event's own duration — not stored, since the "
             "event's duration keeps moving until it is stopped.")
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', readonly=True)
    fmes_cost = fields.Monetary(
        string='Cost', currency_field='currency_id',
        groups='furnishing_mes.group_fmes_manager',
        help="Parts and labour. Optional — tracked when the plant has the "
             "figure, never forced (assumption A22).")
    fmes_checklist_result_ids = fields.One2many(
        'fmes.maintenance.checklist.result', 'request_id',
        string='Checklist')

    @api.depends('fmes_productivity_id.duration')
    def _compute_fmes_downtime_hours(self):
        for request in self:
            request.fmes_downtime_hours = (
                request.fmes_productivity_id.duration or 0.0) / 60.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            equipment_id = vals.get('equipment_id')
            if equipment_id and not vals.get('workcenter_id'):
                equipment = self.env['maintenance.equipment'].browse(
                    equipment_id)
                if equipment.workcenter_id:
                    vals['workcenter_id'] = equipment.workcenter_id.id
        return super().create(vals_list)

    def write(self, vals):
        becoming_done = False
        if 'stage_id' in vals:
            becoming_done = bool(
                self.env['maintenance.stage'].browse(vals['stage_id']).done)
        res = super().write(vals)
        if becoming_done:
            preventive = self.filtered(
                lambda r: r.fmes_schedule_id
                and r.maintenance_type == 'preventive')
            for request in preventive:
                request.fmes_schedule_id._fmes_mark_done(
                    request.close_date or fields.Date.context_today(request))
        return res
