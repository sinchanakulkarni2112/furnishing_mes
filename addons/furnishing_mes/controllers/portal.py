# -*- coding: utf-8 -*-
"""Customer portal (Phase 13): order tracking, support tickets, and the
order form that puts a fresh customer order in front of the factory.

Extends Odoo's native `CustomerPortal` rather than building a parallel
portal from scratch (ADR-001) — `/my/orders` and its order detail page
already exist, fully partner-filtered, courtesy of `sale`'s own portal
controller; this module adds the `/my/tickets` surface (there is no
Community ticketing to extend), a `ticket_count` tile on `/my/home`,
following exactly the same pattern `sale` itself uses for `order_count`,
and `/my/orders/new`, the one route here that CREATES a document: an
order placed through it is flagged `fmes_from_portal`, which is what the
new-order-received alert automation filters on, and the confirmed line it
writes is picked up by the planning engine's demand collector and the
dashboard's incoming-demand tile.

Every route here that takes a document id goes through `_document_check_
access`, native portal.mixin machinery: it checks `check_access('read')`
against the CURRENT (non-sudo) user, so a portal customer requesting
another partner's ticket id gets exactly the same `AccessError` ->
redirect-to-`/my` a portal customer already gets for another partner's
sale order — the record rule in `security/fmes_record_rules.xml` is what
actually enforces the ownership boundary, this controller only decides
what to do when that check fails.
"""

import math

from odoo import _, fields, http
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

TICKETS_PER_PAGE = 20


class FmesPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'ticket_count' in counters:
            Ticket = request.env['fmes.support.ticket']
            values['ticket_count'] = (
                Ticket.search_count(self._ticket_domain(
                    request.env.user.partner_id))
                if Ticket.has_access('read') else 0)
        if 'production_report_count' in counters:
            SaleOrder = request.env['sale.order']
            values['production_report_count'] = (
                SaleOrder.search_count(self._production_report_domain(
                    request.env.user.partner_id))
                if SaleOrder.has_access('read') else 0)
        return values

    def _ticket_domain(self, partner):
        # child_of + commercial_partner_id, not a plain partner_id match:
        # a ticket raised by any contact at the customer's company should
        # be visible to every portal login at that same company, the exact
        # rule sale.order's own native portal domain already uses
        # (sale/controllers/portal.py's _prepare_orders_domain) — mirrored
        # here, and in the matching ir.rule in fmes_record_rules.xml, so
        # the controller's own domain and the record rule can never disagree.
        return [('partner_id', 'child_of', [partner.commercial_partner_id.id])]

    # ------------------------------------------------------------
    # Ticket list
    # ------------------------------------------------------------
    def _ticket_searchbar_sortings(self):
        return {
            'date': {'label': _('Newest'), 'order': 'create_date desc'},
            'state': {'label': _('Status'), 'order': 'state, create_date desc'},
        }

    @http.route(
        ['/my/tickets', '/my/tickets/page/<int:page>'],
        type='http', auth='user', website=True)
    def portal_my_tickets(self, page=1, sortby='date', **kwargs):
        Ticket = request.env['fmes.support.ticket']
        partner = request.env.user.partner_id
        domain = self._ticket_domain(partner)

        searchbar_sortings = self._ticket_searchbar_sortings()
        sortby = sortby if sortby in searchbar_sortings else 'date'
        sort_order = searchbar_sortings[sortby]['order']

        ticket_count = Ticket.search_count(domain)
        pager_values = portal_pager(
            url='/my/tickets', total=ticket_count, page=page,
            step=TICKETS_PER_PAGE)
        tickets = Ticket.search(
            domain, order=sort_order, limit=TICKETS_PER_PAGE,
            offset=pager_values['offset'])
        request.session['my_tickets_history'] = tickets.ids[:100]

        return request.render('furnishing_mes.portal_my_tickets', {
            'tickets': tickets,
            'page_name': 'ticket',
            'pager': pager_values,
            'default_url': '/my/tickets',
            'sortby': sortby,
            'searchbar_sortings': searchbar_sortings,
        })

    # ------------------------------------------------------------
    # New ticket
    # ------------------------------------------------------------
    @http.route(
        ['/my/tickets/new'], type='http', auth='user', website=True,
        methods=['GET', 'POST'])
    def portal_ticket_new(self, **kwargs):
        partner = request.env.user.partner_id
        error = {}
        if request.httprequest.method == 'POST':
            subject = (kwargs.get('subject') or '').strip()
            if not subject:
                error['subject'] = _(
                    "Please describe the issue in a few words.")
            else:
                Ticket = request.env['fmes.support.ticket']
                categories = dict(Ticket._fields['category'].selection)
                ticket = Ticket.create({
                    'partner_id': partner.id,
                    'subject': subject,
                    'description': kwargs.get('description'),
                    'category': (kwargs.get('category')
                                if kwargs.get('category') in categories
                                else 'other'),
                })
                return request.redirect('/my/tickets/%d' % ticket.id)

        return request.render('furnishing_mes.portal_ticket_new', {
            'error': error,
            'ticket_categories': dict(
                request.env['fmes.support.ticket']
                ._fields['category'].selection),
            'form_values': kwargs,
            'page_name': 'ticket',
        })

    # ------------------------------------------------------------
    # Ticket detail
    # ------------------------------------------------------------
    def _ticket_get_page_view_values(self, ticket_sudo, access_token, **kwargs):
        values = {'page_name': 'ticket', 'ticket': ticket_sudo}
        return self._get_page_view_values(
            ticket_sudo, access_token, values, 'my_tickets_history', False,
            **kwargs)

    @http.route(
        ['/my/tickets/<int:ticket_id>'], type='http', auth='user',
        website=True)
    def portal_ticket_page(self, ticket_id, access_token=None, **kwargs):
        try:
            ticket_sudo = self._document_check_access(
                'fmes.support.ticket', ticket_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = self._ticket_get_page_view_values(
            ticket_sudo, access_token, **kwargs)
        return request.render('furnishing_mes.portal_ticket_page', values)

    # ------------------------------------------------------------
    # Production report — one of the Customer Dashboard's five buttons
    # (docs/`Product visualization`): "Production Report" distinct from
    # "Track Progress" (the per-order inline section below) and "Your
    # Orders" (sale's own native /my/orders) — a single consolidated page
    # across every one of the customer's own confirmed orders, instead of
    # having to open each order individually to see its progress.
    # ------------------------------------------------------------
    def _production_report_domain(self, partner):
        # Same child_of + commercial_partner_id + confirmed-only shape
        # sale.order's own native portal domain uses (this file's own
        # docstring) and _ticket_domain already mirrors — a contact at the
        # customer's company sees every one of that company's orders, not
        # just ones placed by their own exact login.
        return [
            ('partner_id', 'child_of', [partner.commercial_partner_id.id]),
            ('state', '=', 'sale'),
        ]

    @http.route(['/my/production-report'], type='http', auth='user', website=True)
    def portal_production_report(self, **kwargs):
        SaleOrder = request.env['sale.order']
        partner = request.env.user.partner_id
        orders = SaleOrder.search(
            self._production_report_domain(partner), order='date_order desc')
        return request.render('furnishing_mes.portal_production_report', {
            'orders': orders,
            'page_name': 'production_report',
        })

    # ------------------------------------------------------------
    # New order — the customer places it, the factory sees it
    # ------------------------------------------------------------
    # The whole route is written to be boring on purpose: every value that
    # reaches the ORM is either validated against a whitelist right here or
    # derived from the logged-in user, and nothing else is read out of the
    # request. In particular price_unit and discount are NEVER taken from
    # the form — sale.order.line computes them server-side from the
    # customer's own pricelist (`_compute_price_unit`, store=True,
    # precompute=True), so a tampered price/discount field in the POST
    # body is simply never looked at.
    # ------------------------------------------------------------
    @staticmethod
    def _portal_order_product_domain():
        """The only products a portal customer may order: saleable goods.

        `type != 'service'` is the same filter the planning engine's
        `_collect_sale_order_demand` applies — an order line the factory
        can never manufacture has no business being placed here either.
        """
        return [('sale_ok', '=', True),
                ('type', '!=', 'service'),
                ('active', '=', True)]

    def _portal_order_product(self, raw, error):
        try:
            product_id = int(raw)
        except (TypeError, ValueError):
            product_id = 0
        # sudo: base.group_portal has no read ACL on product.product
        # (product/security/ir.model.access.csv) and the form must list
        # the factory's catalogue. Restricting the search to the whitelisted
        # domain above is what makes this safe: a product id that is not a
        # live, saleable, manufacturable good simply matches nothing.
        product = request.env['product.product'].sudo().search(
            [('id', '=', product_id)] + self._portal_order_product_domain(),
            limit=1)
        if not product:
            error['product_id'] = _('That product cannot be ordered here.')
            return request.env['product.product'].sudo()
        return product

    def _portal_order_qty(self, raw, error):
        try:
            qty = float(raw)
        except (TypeError, ValueError):
            qty = 0.0
        if not math.isfinite(qty) or qty <= 0:
            error['product_uom_qty'] = _('Quantity must be greater than zero.')
            return 0.0
        return qty

    def _portal_order_commitment_date(self, raw, error):
        if not raw:
            return False
        try:
            return fields.Datetime.to_datetime(fields.Date.to_date(raw))
        except (TypeError, ValueError, AttributeError):
            error['requested_delivery_date'] = _('That delivery date could '
                                                  'not be read.')
            return False

    def _create_portal_order(self, partner, product, qty, commitment_date,
                             order_state):
        """Build and optionally confirm the customer's own order.

        `sudo()` is required and safe by construction, and both halves of
        that claim are worth spelling out:

        - Required: portal's ACL on sale.order / sale.order.line is READ-
          only (sale/security/ir.model.access.csv), so a portal login
          cannot create or confirm an order with its own rights.
        - Safe: the vals dicts below are written from scratch out of the
          validated parameters above — the partner is the logged-in user's
          own partner (never a request field), the price is whatever the
          server-side pricelist compute decides, and no key of the POST
          body is forwarded. Company follows the partner's company.
        """
        SaleOrder = request.env['sale.order'].sudo()
        order = SaleOrder.create({
            'partner_id': partner.id,
            'commitment_date': commitment_date,
            'fmes_from_portal': True,
        })
        # sale's native portal record rule scopes on message_partner_ids
        # (followers), not partner_id: without this the customer who just
        # placed the order cannot even open their own confirmation page.
        order.message_subscribe(partner_ids=[partner.id])
        request.env['sale.order.line'].sudo().create({
            'order_id': order.id,
            'product_id': product.id,
            'product_uom_qty': qty,
        })
        if order_state == 'confirmed':
            order.action_confirm()
        return order

    @http.route(
        ['/my/orders/new'], type='http', auth='user', website=True,
        methods=['GET', 'POST'])
    def portal_order_new(self, **kwargs):
        partner = request.env.user.partner_id
        error = {}
        form_values = {
            'product_id': kwargs.get('product_id') or '',
            'product_uom_qty': kwargs.get('product_uom_qty') or '',
            'requested_delivery_date': (
                kwargs.get('requested_delivery_date') or ''),
            'order_state': kwargs.get('order_state') or 'draft',
        }

        if request.httprequest.method == 'POST':
            product = self._portal_order_product(
                kwargs.get('product_id'), error)
            qty = self._portal_order_qty(kwargs.get('product_uom_qty'), error)
            commitment_date = self._portal_order_commitment_date(
                kwargs.get('requested_delivery_date'), error)
            order_state = form_values['order_state']
            if order_state not in ('draft', 'confirmed'):
                error['order_state'] = _('Please choose how to place the '
                                         'order.')
            if not error:
                order = self._create_portal_order(
                    partner, product, qty, commitment_date, order_state)
                return request.redirect('/my/orders/%d' % order.id)

        products = request.env['product.product'].sudo().search(
            self._portal_order_product_domain(), order='name')
        return request.render('furnishing_mes.portal_order_new', {
            'error': error,
            'form_values': form_values,
            'products': products,
            'order_states': [
                ('draft', _('Save it as a quotation')),
                ('confirmed', _('Place the order now')),
            ],
            'page_name': 'order',
        })
