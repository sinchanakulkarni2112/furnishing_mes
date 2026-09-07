# -*- coding: utf-8 -*-
"""Operator machine scoping.

An operator should only see and touch the machines they actually work on. The
security model derives that from the daily roster, which arrives with operator
allocation in Phase 8.

Until then the assignment is explicit: an administrator lists the machines an
operator may work on. That is real scoping rather than a placeholder, it stays
useful once the roster exists (a permanent assignment and a day's allocation
are different things), and it means the terminal is safe from the day it ships.

When no machines are assigned, an operator is not locked out — they may record
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
        help="The machines this user may work on right now. Phase 8 adds the "
             "day's roster as a second source; nothing that reads this field "
             "has to change when it does.")
    fmes_has_machine_scope = fields.Boolean(
        compute='_compute_fmes_allowed_workcenter_ids',
        help="True when the user's machines have been restricted at all.")

    @api.depends('fmes_workcenter_ids', 'fmes_department_ids')
    def _compute_fmes_allowed_workcenter_ids(self):
        Workcenter = self.env['mrp.workcenter']
        for user in self:
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
