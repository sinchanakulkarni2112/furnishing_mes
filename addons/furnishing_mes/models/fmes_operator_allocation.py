# -*- coding: utf-8 -*-
"""Daily operator roster (Requirement 8.1).

One row = one employee, one machine, one shift, one day. This is also the
model that makes operator machine-scoping real: `res.users.
fmes_allowed_workcenter_ids` reads today's rows for the current user's own
employee record, ahead of the permanent `fmes_workcenter_ids` assignment
Phase 4 shipped with — the day's actual roster is more current than a
standing default, and the standing default stays as the fallback for a plant
that has not started rostering yet.
"""

from datetime import timedelta

from odoo import _, api, fields, models

ROLES = [
    ('operator', 'Operator'),
    ('helper', 'Helper'),
    ('setter', 'Setter'),
    ('inspector', 'Inspector'),
]

STATES = [
    ('planned', 'Planned'),
    ('present', 'Present'),
    ('absent', 'Absent'),
    ('reassigned', 'Reassigned'),
]


class FmesOperatorAllocation(models.Model):
    _name = 'fmes.operator.allocation'
    _description = 'Operator Allocation'
    _order = 'date desc, shift_id, workcenter_id'
    _rec_name = 'employee_id'

    date = fields.Date(required=True, index=True)
    shift_id = fields.Many2one(
        'fmes.shift', string='Shift', required=True, index=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, index=True)
    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Machine', required=True, index=True)
    department_id = fields.Many2one(
        related='workcenter_id.department_id', store=True, readonly=True,
        string='Department')
    role = fields.Selection(
        ROLES, default='operator', required=True)
    state = fields.Selection(
        STATES, default='planned', required=True,
        help="Absent is the only status excluded from the operator's "
             "machine scope and from the planning engine's manpower "
             "factor — planned and reassigned both still mean 'here'.")
    hours = fields.Float(help="Defaults from the shift's own net hours.")
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('fmes_allocation_slot_uniq',
         'unique(date, shift_id, employee_id)',
         'This employee is already allocated for this shift on this date. '
         'Change their machine on the existing row instead of creating a '
         'second one — a reassignment, not a duplicate.'),
    ]

    @api.onchange('shift_id')
    def _onchange_shift_id(self):
        if self.shift_id:
            self.hours = self.shift_id.net_hours

    # ==================================================================
    # Bulk copy-previous-week (Requirement 8, deliverable 3)
    # ==================================================================
    def action_copy_to_next_week(self):
        """Duplicate the selected rows exactly 7 days later, reset to
        'planned'. Safe to run more than once: a target slot that already
        has an allocation is simply skipped rather than duplicated."""
        Allocation = self.env['fmes.operator.allocation']
        created = Allocation
        for row in self:
            target_date = row.date + timedelta(days=7)
            clash = Allocation.search([
                ('date', '=', target_date),
                ('shift_id', '=', row.shift_id.id),
                ('employee_id', '=', row.employee_id.id),
            ], limit=1)
            if clash:
                continue
            created |= row.copy({'date': target_date, 'state': 'planned'})
        skipped = len(self) - len(created)
        message = _(
            "%(count)s roster row(s) copied to next week.",
            count=len(created))
        if skipped:
            message = _(
                "%(count)s roster row(s) copied to next week "
                "(%(skipped)s already had an allocation and were skipped).",
                count=len(created), skipped=skipped)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Roster Copied'),
                'message': message,
                'type': 'success',
                'sticky': False,
            },
        }
