# -*- coding: utf-8 -*-
"""Operator machine scoping.

An operator should only see and touch the machines they actually work on.
Three sources, checked in order of how current they are:

1. Today's roster (`fmes.operator.allocation`, Phase 8) — the actual plan for
   today, for the employee linked to this user. Excludes only 'absent';
   'planned' and 'reassigned' both still mean "here today."
2. The permanent assignment (`fmes_workcenter_ids`, Phase 4) — a standing
   default for a plant that has not started rostering a given day yet, or
   for a user with no linked employee at all.
3. The department-wide fallback (`fmes_department_ids`) when neither of the
   above narrows it down.

When none of the three apply, an operator is not locked out — they may record
on any machine but can only ever see **their own** entries. Locking every
operator out of an unconfigured system would make the terminal unusable on day
one; letting them see everyone's work would be worse.
"""

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    fmes_workcenter_ids = fields.Many2many(
        'mrp.workcenter',
        'fmes_user_workcenter_rel', 'user_id', 'workcenter_id',
        string='Assigned Machines',
        help="Machines this user may record production on. Leave empty and the "
             "user can record anywhere but will only see their own entries.")
    fmes_department_ids = fields.Many2many(
        'hr.department',
        'fmes_user_department_rel', 'user_id', 'department_id',
        string='Assigned Departments',
        help="Departments a supervisor is responsible for. Leave empty for all. "
             "Used by the department-scoped record rules from Phase 8.")
    fmes_allowed_workcenter_ids = fields.Many2many(
        'mrp.workcenter', compute='_compute_fmes_allowed_workcenter_ids',
        string='Allowed Machines',
        help="The machines this user may work on right now: today's roster "
             "if one exists, else the permanent assignment, else the "
             "department fallback.")
    fmes_has_machine_scope = fields.Boolean(
        compute='_compute_fmes_allowed_workcenter_ids',
        help="True when the user's machines have been restricted at all.")

    @api.depends('fmes_workcenter_ids', 'fmes_department_ids')
    def _compute_fmes_allowed_workcenter_ids(self):
        # Not fully expressible as an @api.depends path: today's roster
        # lives on a different model, joined only by employee_id and the
        # current date, not a real relational field from res.users. Same
        # reasoning as mrp.workcenter's own "not stored, a view of the
        # present" computes (Phase 4/6) — read fresh, not cached long.
        Workcenter = self.env['mrp.workcenter']
        Allocation = self.env['fmes.operator.allocation']
        today = fields.Date.context_today(self)
        for user in self:
            machines = Workcenter.browse()
            if user.employee_id:
                todays_rows = Allocation.search([
                    ('employee_id', '=', user.employee_id.id),
                    ('date', '=', today),
                    ('state', '!=', 'absent'),
                ])
                machines = todays_rows.workcenter_id
            if not machines:
                machines = user.fmes_workcenter_ids
            if not machines and user.fmes_department_ids:
                machines = Workcenter.search(
                    [('department_id', 'in', user.fmes_department_ids.ids)])
            user.fmes_allowed_workcenter_ids = machines
            user.fmes_has_machine_scope = bool(machines)

    @property
    def SELF_READABLE_FIELDS(self):
        # The terminal reads the current user's own scope to build the machine
        # picker; without this an operator cannot read it about themselves.
        return super().SELF_READABLE_FIELDS + [
            'fmes_workcenter_ids', 'fmes_department_ids',
            'fmes_allowed_workcenter_ids', 'fmes_has_machine_scope',
        ]
