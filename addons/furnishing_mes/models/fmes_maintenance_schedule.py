# -*- coding: utf-8 -*-
"""Preventive maintenance scheduling (Requirement 7.2).

A `fmes.maintenance.schedule` is a template, not a request — it never appears
on anyone's work queue by itself. `_cron_generate_due_requests` (wired to
`fmes_generate_preventive_requests` in data/fmes_crons.xml) converts a due
schedule into a real `maintenance.request`, so all maintenance history — PM
and breakdown alike — lives in the one native model Odoo's own MTBF/MTTR
already read.

Two trigger types (deliverable 3):

- `time_based` — `next_due_date` is a plain calendar computation from
  `last_done_date` (or the equipment's own commissioning date, before the
  first cycle) plus the interval. Purely declarative; recomputes itself
  whenever those fields change.
- `usage_based` — due when accumulated *run hours* since the last visit cross
  `usage_threshold_hours`. There is no fixed calendar date to compute this
  from in advance (it depends on a future, unknown run rate), so unlike the
  time-based branch this is not something `@api.depends` can express: the
  cron's own `_check_usage_triggers` imperatively checks accumulated hours
  each run and stamps `next_due_date` to today the moment the threshold is
  crossed (assumption A51 — see docs/15). Until then `next_due_date` stays
  unset, which correctly reads as "not yet due" everywhere else in the
  module rather than as an overdue date in the distant past.
"""

from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

INTERVAL_UNITS = [
    ('day', 'Days'),
    ('week', 'Weeks'),
    ('month', 'Months'),
    ('year', 'Years'),
]

TRIGGER_TYPES = [
    ('time_based', 'Time-Based'),
    ('usage_based', 'Usage-Based'),
]

SCHEDULE_STATES = [
    ('active', 'Active'),
    ('paused', 'Paused'),
    ('archived', 'Archived'),
]


class FmesMaintenanceSchedule(models.Model):
    _name = 'fmes.maintenance.schedule'
    _description = 'Preventive Maintenance Schedule'
    _order = 'next_due_date, name'
    _inherit = ['mail.thread']

    name = fields.Char(
        required=True, tracking=True,
        default=lambda self: self.env['ir.sequence'].next_by_code(
            'fmes.maintenance.schedule') or _('New'))
    equipment_id = fields.Many2one(
        'maintenance.equipment', string='Equipment', required=True,
        tracking=True, index=True)
    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Machine', related='equipment_id.workcenter_id',
        store=True, readonly=True, index=True)
    maintenance_team_id = fields.Many2one(
        'maintenance.team', string='Maintenance Team')
    trigger_type = fields.Selection(
        TRIGGER_TYPES, default='time_based', required=True, tracking=True)
    interval_number = fields.Integer(
        string='Repeat Every', default=1,
        help="Used when trigger type is time-based.")
    interval_unit = fields.Selection(
        INTERVAL_UNITS, default='month',
        help="Used when trigger type is time-based.")
    usage_threshold_hours = fields.Float(
        string='Usage Threshold (hours)',
        help="Run hours since the last visit that trigger this schedule. "
             "Used when trigger type is usage-based.")
    last_done_date = fields.Date(
        string='Last Done', tracking=True,
        help="Set automatically when the generated request is marked done.")
    next_due_date = fields.Date(
        compute='_compute_next_due_date', store=True, readonly=False,
        index=True, tracking=True, copy=False)
    lead_time_days = fields.Integer(
        string='Lead Time (days)', default=7,
        help="How many days before the due date the request is raised "
             "(assumption A20, docs/15-open-questions-and-assumptions.md).")
    estimated_duration_hours = fields.Float(string='Estimated Duration (hrs)')
    checklist_ids = fields.One2many(
        'fmes.maintenance.checklist.line', 'schedule_id', string='Checklist')
    request_ids = fields.One2many(
        'maintenance.request', 'fmes_schedule_id', string='Generated Requests')
    request_count = fields.Integer(
        compute='_compute_request_count', string='Requests')
    state = fields.Selection(
        SCHEDULE_STATES, default='active', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('last_done_date', 'interval_number', 'interval_unit',
                 'trigger_type', 'equipment_id.effective_date')
    def _compute_next_due_date(self):
        today = fields.Date.context_today(self)
        for schedule in self:
            if schedule.trigger_type != 'time_based':
                # Usage-based due dates are stamped imperatively by the
                # cron's own usage check, not derived from a calendar
                # interval — see the module docstring. A fresh cycle (this
                # recompute fires whenever last_done_date changes, i.e. on
                # every completion) starts with no known due date again.
                schedule.next_due_date = False
                continue
            anchor = (schedule.last_done_date
                      or schedule.equipment_id.effective_date or today)
            unit = schedule.interval_unit or 'month'
            number = schedule.interval_number or 1
            schedule.next_due_date = anchor + relativedelta(
                **{f'{unit}s': number})

    @api.depends('request_ids')
    def _compute_request_count(self):
        counts = dict(self.env['maintenance.request']._read_group(
            [('fmes_schedule_id', 'in', self.ids)],
            groupby=['fmes_schedule_id'], aggregates=['__count'])) \
            if self.ids else {}
        for schedule in self:
            schedule.request_count = counts.get(schedule, 0)

    # ==================================================================
    # Usage-based triggering (Requirement 7, deliverable 3)
    # ==================================================================
    def _fmes_run_hours_since(self, since_date):
        """Approved productive hours logged on this schedule's machine
        since `since_date` — the same source docs/11's own "Run hours"
        metric uses (`loss_type = 'productive'`, approved only)."""
        self.ensure_one()
        if not self.workcenter_id or not since_date:
            return 0.0
        events = self.env['mrp.workcenter.productivity'].search([
            ('workcenter_id', '=', self.workcenter_id.id),
            ('loss_type', '=', 'productive'),
            ('fmes_state', '=', 'approved'),
            ('date_end', '!=', False),
            ('date_start', '>=', since_date),
        ])
        return sum(events.mapped('duration')) / 60.0

    def _check_usage_triggers(self):
        """Stamp `next_due_date` to today for any usage-based schedule
        whose accumulated run hours have crossed its threshold. Only
        touches schedules with no due date yet — one already due is left
        alone until it is fulfilled and the next cycle begins."""
        today = fields.Date.context_today(self)
        candidates = self.filtered(
            lambda s: s.state == 'active' and s.trigger_type == 'usage_based'
            and not s.next_due_date and s.usage_threshold_hours > 0)
        for schedule in candidates:
            since = (schedule.last_done_date
                     or schedule.equipment_id.effective_date)
            hours = schedule._fmes_run_hours_since(since)
            if hours >= schedule.usage_threshold_hours:
                schedule.next_due_date = today

    # ==================================================================
    # Preventive request generation (Requirement 7, deliverable 2)
    # ==================================================================
    @api.model
    def _cron_generate_due_requests(self):
        schedules = self.search([('state', '=', 'active')])
        schedules._check_usage_triggers()
        schedules._generate_due_requests()

    def _generate_due_requests(self):
        """Raise a request for every schedule due within its own lead
        time, unless one it already raised is still open — a plant that
        runs this cron daily must never see two open requests for the
        same visit just because nobody has closed the first one yet."""
        today = fields.Date.context_today(self)
        for schedule in self:
            if schedule.state != 'active' or not schedule.next_due_date:
                continue
            horizon = schedule.next_due_date - timedelta(
                days=schedule.lead_time_days or 0)
            if today < horizon:
                continue
            if schedule.request_ids.filtered(lambda r: not r.close_date):
                continue
            schedule._create_request()

    def _create_request(self):
        self.ensure_one()
        Request = self.env['maintenance.request'].sudo()
        vals = {
            'name': _("Preventive: %(schedule)s", schedule=self.name),
            'equipment_id': self.equipment_id.id,
            'workcenter_id': self.workcenter_id.id,
            'maintenance_type': 'preventive',
            'fmes_schedule_id': self.id,
            'fmes_due_date': self.next_due_date,
            'schedule_date': self.next_due_date,
            'duration': self.estimated_duration_hours,
        }
        if self.maintenance_team_id:
            vals['maintenance_team_id'] = self.maintenance_team_id.id
        request = Request.create(vals)
        if self.checklist_ids:
            self.env['fmes.maintenance.checklist.result'].sudo().create([{
                'request_id': request.id,
                'checklist_line_id': line.id,
                'sequence': line.sequence,
                'name': line.name,
                'is_mandatory': line.is_mandatory,
                'expected_value': line.expected_value,
            } for line in self.checklist_ids])
        return request

    # ==================================================================
    # Completion (called from the maintenance.request extension)
    # ==================================================================
    def _fmes_mark_done(self, done_date):
        """`last_done_date` moves; `next_due_date` recomputes on its own
        (it depends on `last_done_date`)."""
        self.write({'last_done_date': done_date})

    def action_view_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generated Requests'),
            'res_model': 'maintenance.request',
            'view_mode': 'list,form,calendar,kanban',
            'domain': [('fmes_schedule_id', '=', self.id)],
        }
