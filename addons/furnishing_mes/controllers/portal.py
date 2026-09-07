# -*- coding: utf-8 -*-
"""Customer portal (Phase 13): order tracking and support tickets.

Extends Odoo's native `CustomerPortal` rather than building a parallel
portal from scratch (ADR-001) — `/my/orders` and its order detail page
already exist, fully partner-filtered, courtesy of `sale`'s own portal
controller; this module only adds the `/my/tickets` surface (there is no
Community ticketing to extend) and a `ticket_count` tile on `/my/home`,
following exactly the same pattern `sale` itself uses for `order_count`.

Every route here that takes a document id goes through `_document_check_
access`, native portal.mixin machinery: it checks `check_access('read')`
against the CURRENT (non-sudo) user, so a portal customer requesting
another partner's ticket id gets exactly the same `AccessError` ->
redirect-to-`/my` a portal customer already gets for another partner's
sale order — the record rule in `security/fmes_record_rules.xml` is what
actually enforces the ownership boundary, this controller only decides
what to do when that check fails.
"""

from odoo import _, http
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
