# -*- coding: utf-8 -*-
"""Shift master.

Shifts are the time dimension of every plan, target and report in the system
(Requirements 1.6 and 2.5). Keeping them as records rather than a hard-coded
selection means the plant can change its shift pattern without a code change —
see assumption A1 in docs/15-open-questions-and-assumptions.md, which is the
standard three-shift pattern we build on until the customer confirms theirs.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def format_float_time(value):
    """Render a float hour (6.5) as a clock string ("06:30")."""
    hours = int(value)
    minutes = int(round((value - hours) * 60))
    if minutes == 60:          # 5.999... must not render as "05:60"
        hours, minutes = hours + 1, 0
    return '%02d:%02d' % (hours % 24, minutes)


class FmesShift(models.Model):
    _name = 'fmes.shift'
    _description = 'Production Shift'
    _order = 'sequence, start_time, id'

    name = fields.Char(
        string='Shift Name', required=True, translate=True,
        help="Display name, for example 'Shift A' or 'General Shift'.")
    code = fields.Char(
        string='Code', required=True, size=8,
        help="Short code used in reports and plan lines, for example 'A'.")
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Colour')

    start_time = fields.Float(
        string='Start', required=True, default=6.0,
        help="Shift start as a 24-hour clock value: 6.5 means 06:30.")
    end_time = fields.Float(
        string='End', required=True, default=14.0,
        help="Shift end. An end earlier than the start means the shift runs "
             "past midnight, which is normal for a night shift.")
    break_minutes = fields.Integer(
        string='Break (minutes)', default=30,
        help="Total break time, deducted from the capacity available for "
             "planning.")

    duration_hours = fields.Float(
        string='Duration', compute='_compute_hours', store=True,
        help="Elapsed hours from start to end, including breaks.")
    net_hours = fields.Float(
        string='Net Hours', compute='_compute_hours', store=True,
        help="Duration minus breaks. This is the figure the planning engine "
             "treats as available capacity.")
    crosses_midnight = fields.Boolean(
        compute='_compute_hours', store=True,
        help="True when the shift ends on the following calendar day.")
    time_range = fields.Char(
        string='Timing', compute='_compute_time_range',
        help="Human-readable shift window.")

    resource_calendar_id = fields.Many2one(
        'resource.calendar', string='Working Calendar',
        help="Optional. Links the shift to an Odoo working calendar for "
             "finite-capacity scheduling.")

    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    note = fields.Text(string='Notes')

    _sql_constraints = [
        ('fmes_shift_code_uniq',
         'unique(code, company_id)',
         'A shift with this code already exists for this company.'),
        ('fmes_shift_break_positive',
         'CHECK(break_minutes >= 0)',
         'Break minutes cannot be negative.'),
    ]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('start_time', 'end_time', 'break_minutes')
    def _compute_hours(self):
        for shift in self:
            start, end = shift.start_time, shift.end_time
            # An end at or before the start means the shift wraps past
            # midnight — the night shift case (22:00 to 06:00).
            crosses = end <= start
            duration = (24.0 - start + end) if crosses else (end - start)
            shift.crosses_midnight = crosses
            shift.duration_hours = duration
            shift.net_hours = duration - (shift.break_minutes or 0) / 60.0

    @api.depends('start_time', 'end_time', 'crosses_midnight')
    def _compute_time_range(self):
        for shift in self:
            suffix = ' (+1d)' if shift.crosses_midnight else ''
            shift.time_range = '%s - %s%s' % (
                format_float_time(shift.start_time),
                format_float_time(shift.end_time),
                suffix)

    @api.depends('name', 'code', 'start_time', 'end_time')
    def _compute_display_name(self):
        for shift in self:
            shift.display_name = '%s (%s)' % (shift.name or '', shift.time_range)

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains('start_time', 'end_time')
    def _check_time_bounds(self):
        for shift in self:
            for label, value in (('start', shift.start_time),
                                 ('end', shift.end_time)):
                if not 0.0 <= value < 24.0:
                    raise ValidationError(_(
                        "Shift %(name)s: the %(label)s time must be between "
                        "00:00 and 23:59.",
                        name=shift.name, label=label))
            if shift.start_time == shift.end_time:
                raise ValidationError(_(
                    "Shift %(name)s: start and end time cannot be identical.",
                    name=shift.name))

    @api.constrains('break_minutes', 'start_time', 'end_time')
    def _check_net_hours_positive(self):
        for shift in self:
            if shift.net_hours <= 0:
                raise ValidationError(_(
                    "Shift %(name)s: breaks (%(mins)s minutes) leave no "
                    "productive time in a %(dur).2f hour shift.",
                    name=shift.name, mins=shift.break_minutes,
                    dur=shift.duration_hours))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for shift, vals in zip(self, vals_list):
            if 'code' not in (default or {}):
                vals['code'] = '%s2' % (shift.code or 'NEW')[:7]
            if 'name' not in (default or {}):
                vals['name'] = _("%s (copy)", shift.name)
        return vals_list
