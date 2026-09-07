# -*- coding: utf-8 -*-
"""Order blocking (Requirement 4.2, deliverable 4).

A supervisor marking an order blocked is the live source of truth; the
nightly backlog snapshot (`fmes.backlog.snapshot`) just photographs it each
night, the same way it photographs quantities and dates. Blocking excludes
the order from the planning engine's auto-scheduling — a blocked order has
no capacity to plan against yet, so offering it a slot would just produce a
plan the plant cannot act on.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

BLOCK_REASONS = [
    ('material', 'Material'),
    ('machine', 'Machine'),
    ('manpower', 'Manpower'),
    ('quality', 'Quality'),
    ('customer_hold', 'Customer Hold'),
    ('other', 'Other'),
]


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    fmes_block_reason = fields.Selection(
        BLOCK_REASONS, string='Block Reason', copy=False,
        groups='furnishing_mes.group_fmes_supervisor',
        help="Set to block this order from auto-scheduling and flag it in "
             "the backlog. Clear it to release the order again.")
    fmes_block_note = fields.Text(
        string='Block Note', copy=False,
        groups='furnishing_mes.group_fmes_supervisor')
    fmes_is_blocked = fields.Boolean(
        compute='_compute_fmes_is_blocked', store=True,
        help="True whenever a block reason is set.")
    fmes_blocked_by = fields.Many2one(
        'res.users', readonly=True, copy=False,
        groups='furnishing_mes.group_fmes_supervisor')
    fmes_blocked_on = fields.Datetime(
        readonly=True, copy=False,
        groups='furnishing_mes.group_fmes_supervisor')

    @api.depends('fmes_block_reason')
    def _compute_fmes_is_blocked(self):
        for production in self:
            production.fmes_is_blocked = bool(production.fmes_block_reason)

    def _check_fmes_supervisor(self):
        if not (self.env.su or self.env.user.has_group(
                'furnishing_mes.group_fmes_supervisor')):
            raise AccessError(_(
                "Blocking or releasing an order is a supervisor's job."))

    def action_fmes_mark_blocked(self, reason, note=None):
        self._check_fmes_supervisor()
        self.write({
            'fmes_block_reason': reason,
            'fmes_block_note': note,
            'fmes_blocked_by': self.env.user.id,
            'fmes_blocked_on': fields.Datetime.now(),
        })

    def action_fmes_clear_block(self):
        self._check_fmes_supervisor()
        self.write({
            'fmes_block_reason': False,
            'fmes_block_note': False,
            'fmes_blocked_by': False,
            'fmes_blocked_on': False,
        })
