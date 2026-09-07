# -*- coding: utf-8 -*-
"""Manpower deployment logging (Requirement 8.1-8.4).

A shift's headcount, logged either against a specific machine or at the
department level — a supervisor covering an assembly line does not always
have a single machine to pin a shortage to. `shortage`/`shortage_pct`/
`utilization_pct` are the same standard-vs-actual maths as everywhere else in
this module (D0.7), just applied to people instead of output.
"""

from odoo import api, fields, models


class FmesManpowerLog(models.Model):
    _name = 'fmes.manpower.log'
    _description = 'Manpower Log'
    _order = 'date desc, shift_id'
    _rec_name = 'department_id'

    date = fields.Date(required=True, index=True)
    shift_id = fields.Many2one(
        'fmes.shift', string='Shift', required=True, index=True)
    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Machine',
        help="Optional — leave blank to log a department's headcount as a "
             "whole rather than against one machine.")
    department_id = fields.Many2one(
        'hr.department', string='Department', required=True, index=True)

    std_manpower = fields.Float(
        string='Standard Manpower',
        help="Defaults from the machine's own standard, or the sum across "
             "the department's machines when no specific machine is set — "
             "always editable, since a real shift's requirement can differ "
             "from the standard.")
    actual_manpower = fields.Float(string='Actual Manpower')
    absent_count = fields.Integer(string='Absent')
    overtime_hours = fields.Float()
    reason = fields.Text(
        help="Why actual differs from standard — short-staffed, an "
             "extra hand pulled in, planned leave, ...")

    shortage = fields.Float(
        compute='_compute_shortage', store=True,
        help="Standard minus actual. Positive means short-staffed; negative "
             "means overstaffed.")
    shortage_pct = fields.Float(
        string='Shortage %', compute='_compute_shortage', store=True,
        aggregator=None)
    utilization_pct = fields.Float(
        string='Manpower Utilisation %', compute='_compute_shortage',
        store=True, aggregator=None,
        help="Actual over standard, Requirement 8.4.")

    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    @api.depends('std_manpower', 'actual_manpower')
    def _compute_shortage(self):
        for log in self:
            log.shortage = log.std_manpower - log.actual_manpower
            log.shortage_pct = (
                log.shortage / log.std_manpower * 100.0
                if log.std_manpower else 0.0)
            log.utilization_pct = (
                log.actual_manpower / log.std_manpower * 100.0
                if log.std_manpower else 0.0)

    @api.onchange('workcenter_id')
    def _onchange_workcenter_id(self):
        if self.workcenter_id:
            if self.workcenter_id.department_id:
                self.department_id = self.workcenter_id.department_id
            self.std_manpower = self.workcenter_id.fmes_std_manpower

    @api.onchange('department_id')
    def _onchange_department_id(self):
        if self.department_id and not self.workcenter_id:
            machines = self.env['mrp.workcenter'].search(
                [('department_id', '=', self.department_id.id)])
            self.std_manpower = sum(machines.mapped('fmes_std_manpower'))
