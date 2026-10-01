# -*- coding: utf-8 -*-
"""Plan generator wizard.

The screen a planner actually uses. It shows demand against capacity *before*
anything is created, because the useful answer is often "this week is 130%
loaded" rather than a plan that quietly drops a third of the orders.
"""

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class FmesPlanGenerator(models.TransientModel):
    _name = 'fmes.plan.generator'
    _description = 'Generate Production Plan'

    date_from = fields.Date(
        required=True, default=lambda self: fields.Date.context_today(self))
    date_to = fields.Date(required=True, default=lambda self: (
        fields.Date.context_today(self) + timedelta(days=6)))
    plan_type = fields.Selection(
        [('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly')],
        required=True, default='weekly')
    department_ids = fields.Many2many(
        'hr.department', string='Departments',
        help="Leave empty to plan every department.")
    demand_source = fields.Selection(
        [('open_mo', 'Open Manufacturing Orders'),
         ('mo_and_so', 'Manufacturing Orders and Confirmed Sales Orders')],
        required=True, default='open_mo',
        help="Sales orders without a manufacturing order can be included to "
             "show committed demand earlier.")
    include_carry_forward = fields.Boolean(
        string='Include Carry Forward', default=True,
        help="Bring unfinished work from earlier released plans into this one, "
             "ahead of new orders.")

    # -------------------------------------------------- preview (computed)
    demand_count = fields.Integer(compute='_compute_preview', string='Demands')
    carry_forward_count = fields.Integer(
        compute='_compute_preview', string='Carried Forward')
    unrated_count = fields.Integer(
        compute='_compute_preview', string='Without a Rate',
        help="Demands whose product has no capacity rate on any machine. "
             "These cannot be planned until the capacity matrix covers them.")
    required_hours = fields.Float(
        compute='_compute_preview', string='Hours Required')
    available_hours = fields.Float(
        compute='_compute_preview', string='Hours Available')
    utilization_pct = fields.Float(
        compute='_compute_preview', string='Projected Utilisation %')
    machine_shift_slots = fields.Integer(
        compute='_compute_preview', string='Machine-Shift Slots')
    preview_warning = fields.Char(compute='_compute_preview')

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)

    @api.depends('date_from', 'date_to', 'department_ids', 'demand_source',
                 'include_carry_forward', 'company_id')
    def _compute_preview(self):
        engine = self.env['fmes.planning.engine']
        for wizard in self:
            if not (wizard.date_from and wizard.date_to
                    and wizard.date_from <= wizard.date_to):
                wizard._reset_preview()
                continue
            data = engine.preview(
                wizard.date_from, wizard.date_to,
                departments=wizard.department_ids or None,
                demand_source=wizard.demand_source,
                include_carry_forward=wizard.include_carry_forward,
                company=wizard.company_id)
            wizard.demand_count = data['demand_count']
            wizard.carry_forward_count = data['carry_forward_count']
            wizard.unrated_count = data['unrated_count']
            wizard.required_hours = data['required_hours']
            wizard.available_hours = data['available_hours']
            wizard.utilization_pct = data['utilization_pct']
            wizard.machine_shift_slots = data['machine_shift_slots']
            wizard.preview_warning = wizard._build_warning(data)

    def _reset_preview(self):
        self.demand_count = 0
        self.carry_forward_count = 0
        self.unrated_count = 0
        self.required_hours = 0.0
        self.available_hours = 0.0
        self.utilization_pct = 0.0
        self.machine_shift_slots = 0
        self.preview_warning = False

    def _build_warning(self, data):
        if not data['machine_shift_slots']:
            return _("No machine-shift capacity in this range. Check that "
                     "shifts are defined and machines are active.")
        if data['utilization_pct'] > 100.0:
            return _("Demand exceeds capacity for this period. The plan will "
                     "cover what fits and list the rest as unscheduled.")
        if data['unrated_count']:
            return _("%(count)s demand item(s) have no capacity rate and will "
                     "be left unscheduled.", count=data['unrated_count'])
        return False

    @api.onchange('plan_type', 'date_from')
    def _onchange_plan_type(self):
        """Offer an end date that matches the chosen plan type."""
        for wizard in self:
            if not wizard.date_from:
                continue
            if wizard.plan_type == 'daily':
                wizard.date_to = wizard.date_from
            elif wizard.plan_type == 'weekly':
                wizard.date_to = wizard.date_from + timedelta(days=6)
            else:
                wizard.date_to = wizard.date_from + timedelta(days=29)

    def action_generate(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_("The start date must not be after the end date."))
        if not self.machine_shift_slots:
            raise UserError(_(
                "There is no machine-shift capacity in this range. Define at "
                "least one shift and one active machine before planning."))

        plan = self.env['fmes.planning.engine'].generate(
            self.date_from, self.date_to,
            plan_type=self.plan_type,
            departments=self.department_ids or None,
            demand_source=self.demand_source,
            include_carry_forward=self.include_carry_forward,
            company=self.company_id)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Production Plan'),
            'res_model': 'fmes.production.plan',
            'res_id': plan.id,
            'view_mode': 'form',
        }
