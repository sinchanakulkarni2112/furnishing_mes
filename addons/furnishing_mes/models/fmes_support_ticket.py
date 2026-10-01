# -*- coding: utf-8 -*-
"""Customer support ticket (Phase 13, docs/03-data-model.md section 9.1).

Helpdesk is Enterprise-only (docs/13-odoo-edition-constraints.md), so this
is a lightweight, purpose-built substitute: enough to let a customer raise
something and follow it through to resolution, nothing more. `mail.thread`
gives the chatter a portal customer replies through (docs/06 deliverable
6, "list and detail with reply"); `portal.mixin` gives the record its own
shareable `/my/tickets/<id>` access URL and access-token machinery, the
same infrastructure `sale.order`'s own portal pages already use.

A customer can create and read their own tickets but not edit them once
raised (docs/04-security-model.md's permission matrix: Customer is RC, not
RW) — a support conversation moves forward through replies and state
changes a supervisor or manager makes, not by the customer silently
rewriting what they originally reported.
"""

from odoo import _, api, fields, models

CATEGORIES = [
    ('order_status', 'Order Status'),
    ('quality', 'Quality'),
    ('delivery', 'Delivery'),
    ('billing', 'Billing'),
    ('other', 'Other'),
]
PRIORITIES = [
    ('low', 'Low'), ('normal', 'Normal'), ('high', 'High'),
]
STATES = [
    ('new', 'New'),
    ('in_progress', 'In Progress'),
    ('waiting_customer', 'Waiting on Customer'),
    ('resolved', 'Resolved'),
    ('closed', 'Closed'),
]


class FmesSupportTicket(models.Model):
    _name = 'fmes.support.ticket'
    _description = 'Support Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        required=True, copy=False, readonly=True, default=lambda self: _('New'))
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, index=True,
        tracking=True)
    subject = fields.Char(required=True, tracking=True)
    description = fields.Text()
    category = fields.Selection(
        CATEGORIES, default='other', required=True, tracking=True)
    priority = fields.Selection(PRIORITIES, default='normal', required=True)
    state = fields.Selection(
        STATES, default='new', required=True, index=True, tracking=True)
    assigned_to = fields.Many2one(
        'res.users', string='Assigned To', tracking=True,
        domain=lambda self: [
            ('groups_id', 'in', self.env.ref(
                'furnishing_mes.group_fmes_supervisor').id)])
    sale_order_id = fields.Many2one(
        'sale.order', string='Sale Order',
        domain="[('partner_id', '=', partner_id)]")
    production_id = fields.Many2one(
        'mrp.production', string='Manufacturing Order')
    resolution = fields.Text()
    closed_on = fields.Datetime(readonly=True, copy=False)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                # sudo(): assigning the next ticket number is bookkeeping,
                # not something that should depend on the creating user's
                # own rights — a portal customer legitimately creates
                # their own ticket (docs/04 permission matrix: Customer is
                # RC) but has no access to ir.sequence at all, the same
                # way any other internal-only sequence works.
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'fmes.support.ticket') or _('New')
        return super().create(vals_list)

    def _compute_access_url(self):
        super()._compute_access_url()
        for ticket in self:
            ticket.access_url = '/my/tickets/%s' % ticket.id

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_start(self):
        self.filtered(lambda t: t.state == 'new').write({'state': 'in_progress'})

    def action_wait_customer(self):
        self.write({'state': 'waiting_customer'})

    def action_resolve(self):
        self.write({'state': 'resolved', 'closed_on': fields.Datetime.now()})

    def action_close(self):
        self.write({'state': 'closed', 'closed_on': fields.Datetime.now()})

    def action_reopen(self):
        self.write({'state': 'in_progress', 'closed_on': False})
