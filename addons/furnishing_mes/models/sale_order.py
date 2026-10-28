# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    fmes_from_portal = fields.Boolean(
        string='Placed via Customer Portal',
        default=False, copy=False, index=True,
        help='Set by the portal order form when the customer places an '
             'order themselves. The new-order-received alert automation '
             'filters on it, so orders the sales team enters in the '
             'backend never reach the factory floor as a "customer '
             'ordered" alert.')
