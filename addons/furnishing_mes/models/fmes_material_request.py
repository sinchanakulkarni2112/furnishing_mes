# -*- coding: utf-8 -*-
"""Material request (Requirement 6).

The doc's own WorkCentre Downtimes flow: reviewing a downtime report, if no
maintenance is needed a supervisor can "put in a new request for more
materials which will also need Plant manager approval." Same
draft-then-approve shape `mrp.workcenter.productivity.fmes_state` already
establishes for downtime review (Phase 6) — action_approve/action_reject,
approved_by/approved_on stamped only through those actions, a write() guard
refusing a direct state='approved' write that bypasses them, for the same
reason that model's own write() override exists: a record rule sees the
record as it is now, not as the write would make it.

The approver here is the Plant Manager specifically, not the Supervisor —
the doc's own distinction between the supervisor-level downtime review and
this manager-level material approval.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError


STATES = [
    ('new', 'New'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
]


class FmesMaterialRequest(models.Model):
    _name = 'fmes.material.request'
    _description = 'Material Request'
    _inherit = ['mail.thread']
    _order = 'create_date desc'
    _rec_name = 'product_id'

    downtime_event_id = fields.Many2one(
        'mrp.workcenter.productivity', string='Downtime Event',
        ondelete='set null',
        help="The downtime report this request was raised from reviewing, "
             "if any.")
    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Machine', related='downtime_event_id.workcenter_id',
        store=True, readonly=True)
    product_id = fields.Many2one(
        'product.product', string='Material', required=True)
    qty_requested = fields.Float(required=True, digits='Product Unit of Measure')
    notes = fields.Text()
    state = fields.Selection(
        STATES, default='new', required=True, index=True, tracking=True)
    requested_by = fields.Many2one(
        'res.users', default=lambda self: self.env.user, readonly=True)
    approved_by = fields.Many2one(
        'res.users', readonly=True, copy=False,
        groups='furnishing_mes.group_fmes_manager')
    approved_on = fields.Datetime(
        readonly=True, copy=False,
        groups='furnishing_mes.group_fmes_manager')
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    def write(self, vals):
        # Same reasoning as mrp.workcenter.productivity's own write()
        # override: approving must go through action_approve() so
        # approved_by/approved_on can never be missing on an approved
        # record, and so a record rule always sees a state the action
        # actually granted rather than one write() would merely produce.
        if vals.get('state') in ('approved', 'rejected') and not (
                self.env.user.has_group('furnishing_mes.group_fmes_manager')):
            raise AccessError(_(
                "Approving or rejecting a material request is a Plant "
                "Manager's job."))
        return super().write(vals)

    def action_approve(self):
        for request in self:
            request.write({'state': 'approved'})
            request.sudo().write({
                'approved_by': self.env.user.id,
                'approved_on': fields.Datetime.now(),
            })

    def action_reject(self):
        for request in self:
            request.write({'state': 'rejected'})
            request.sudo().write({
                'approved_by': self.env.user.id,
                'approved_on': fields.Datetime.now(),
            })
