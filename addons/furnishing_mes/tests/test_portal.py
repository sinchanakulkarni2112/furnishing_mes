# -*- coding: utf-8 -*-
"""Phase 13 tests: the customer portal (docs/06 deliverable 9).

Three things matter most here, matching docs/04-security-model.md's own
security checklist (T4/T5) and this phase's exit criteria. A portal
customer must see their own data and never another customer's — tested at
the ORM level (`check_access`) and, separately, through real HTTP requests
(`HttpCase`), since a controller bug (forgetting to check ownership before
rendering) would not show up in an ORM-only test. A portal login must
never reach the backend. And "own data" means the whole company, not just
the exact contact who happens to be logged in — `partner_id` on a ticket
or a linked manufacturing order is checked against the user's own
`commercial_partner_id` with `child_of`, the same rule `sale.order`'s own
native portal access already uses, not a literal `partner_id` match (a
first version of this used a literal match and a portal user could not
even read their own company's ticket if it was raised by a different
contact — see D13.x in MEMORY.md).
"""

import re

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged

from .common import FmesTestCase


class PortalCase(FmesTestCase):
    """Two unrelated customers, each with a company partner, a child
    contact who logs in, and a ticket raised under the company itself —
    the exact shape that caught the child-contact ownership bug."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_a = cls.env['res.partner'].create({
            'name': 'Customer A Pvt Ltd', 'is_company': True,
            'customer_rank': 1})
        cls.contact_a = cls.env['res.partner'].create({
            'name': 'Contact A', 'parent_id': cls.partner_a.id,
            'email': 'contact.a@example.com'})
        cls.user_a = cls._create_portal_user(
            'portal_a@example.com', cls.contact_a)

        cls.partner_b = cls.env['res.partner'].create({
            'name': 'Customer B Pvt Ltd', 'is_company': True,
            'customer_rank': 1})
        cls.contact_b = cls.env['res.partner'].create({
            'name': 'Contact B', 'parent_id': cls.partner_b.id,
            'email': 'contact.b@example.com'})
        cls.user_b = cls._create_portal_user(
            'portal_b@example.com', cls.contact_b)

        cls.ticket_a = cls.env['fmes.support.ticket'].create({
            'partner_id': cls.partner_a.id, 'subject': 'A raised this'})
        cls.ticket_b = cls.env['fmes.support.ticket'].create({
            'partner_id': cls.partner_b.id, 'subject': 'B raised this'})

    @classmethod
    def _create_portal_user(cls, login, partner, password='demo12345'):
        return cls.env['res.users'].create({
            'name': partner.name, 'login': login, 'email': login,
            'password': password, 'partner_id': partner.id,
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })

    def _mo_for(self, partner):
        """A manufacturing order linked, via a sale order line, to
        `partner` — the shape `mrp.production.sale_line_id` needs for the
        portal record rule to resolve ownership at all."""
        order = self.env['sale.order'].create({'partner_id': partner.id})
        line = self.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': self.product_wardrobe.id,
            'product_uom_qty': 10.0,
        })
        return self.env['mrp.production'].create({
            'product_id': self.product_wardrobe.id, 'product_qty': 10.0,
            'sale_line_id': line.id,
        }), line


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase13')
class TestTicketOwnership(PortalCase):

    def test_own_companys_ticket_is_readable_by_a_child_contact(self):
        # The ticket is raised under the COMPANY partner; user_a logs in as
        # a CHILD contact of that same company -- must still work.
        self.ticket_a.with_user(self.user_a).check_access('read')

    def test_another_customers_ticket_is_denied(self):
        with self.assertRaises(AccessError):
            self.ticket_b.with_user(self.user_a).check_access('read')

    def test_portal_customer_cannot_write_their_own_ticket(self):
        # RC, not RW (docs/04's permission matrix) -- a customer follows up
        # by replying, not by silently rewriting what they reported.
        with self.assertRaises(AccessError):
            self.ticket_a.with_user(self.user_a).check_access('write')

    def test_portal_customer_can_create_their_own_ticket(self):
        ticket = self.env['fmes.support.ticket'].with_user(self.user_a).create({
            'partner_id': self.contact_a.id, 'subject': 'New issue'})
        self.assertTrue(ticket)

    def test_portal_customer_cannot_create_a_ticket_for_another_company(self):
        with self.assertRaises(AccessError):
            self.env['fmes.support.ticket'].with_user(self.user_a).create({
                'partner_id': self.partner_b.id, 'subject': 'Not mine'})


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase13')
class TestManufacturingOrderOwnership(PortalCase):

    def test_own_manufacturing_order_is_readable(self):
        mo, _line = self._mo_for(self.partner_a)
        mo.with_user(self.user_a).check_access('read')

    def test_another_customers_manufacturing_order_is_denied(self):
        mo, _line = self._mo_for(self.partner_b)
        with self.assertRaises(AccessError):
            mo.with_user(self.user_a).check_access('read')

    def test_manufacturing_order_with_no_sale_line_is_invisible_to_portal(self):
        mo = self.env['mrp.production'].create({
            'product_id': self.product_wardrobe.id, 'product_qty': 10.0})
        with self.assertRaises(AccessError):
            mo.with_user(self.user_a).check_access('read')


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase13')
class TestOrderLineProgress(PortalCase):

    def test_no_linked_production_gives_zero_progress(self):
        order = self.env['sale.order'].create({'partner_id': self.partner_a.id})
        line = self.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': self.product_wardrobe.id,
            'product_uom_qty': 20.0,
        })
        self.assertFalse(line.fmes_production_ids)
        self.assertEqual(line.fmes_produced_qty, 0.0)
        self.assertEqual(line.fmes_progress_pct, 0.0)

    def test_expected_date_falls_back_to_commitment_date(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner_a.id,
            'commitment_date': '2026-06-15 00:00:00',
        })
        line = self.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': self.product_wardrobe.id,
            'product_uom_qty': 5.0,
        })
        self.assertEqual(line.fmes_expected_date.isoformat(), '2026-06-15')

    def test_linked_production_is_found_via_sale_line_id(self):
        mo, line = self._mo_for(self.partner_a)
        self.assertEqual(line.fmes_production_ids, mo)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase13')
class TestPortalHttp(HttpCase):
    """Real HTTP requests -- the only way a controller-level ownership
    bug (as opposed to a record-rule bug) would ever surface."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_a = cls.env['res.partner'].create({
            'name': 'HTTP Customer A', 'is_company': True,
            'customer_rank': 1})
        cls.user_a = cls.env['res.users'].create({
            'name': 'HTTP Contact A', 'login': 'http_portal_a@example.com',
            'email': 'http_portal_a@example.com', 'password': 'demo12345',
            'partner_id': cls.partner_a.id,
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })
        cls.partner_b = cls.env['res.partner'].create({
            'name': 'HTTP Customer B', 'is_company': True,
            'customer_rank': 1})
        cls.ticket_a = cls.env['fmes.support.ticket'].create({
            'partner_id': cls.partner_a.id, 'subject': 'HTTP ticket A'})
        cls.ticket_b = cls.env['fmes.support.ticket'].create({
            'partner_id': cls.partner_b.id, 'subject': 'HTTP ticket B'})

    def test_portal_user_can_open_their_own_ticket(self):
        self.authenticate('http_portal_a@example.com', 'demo12345')
        response = self.url_open('/my/tickets/%d' % self.ticket_a.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'HTTP ticket A', response.content)

    def test_portal_user_is_redirected_away_from_another_customers_ticket(self):
        self.authenticate('http_portal_a@example.com', 'demo12345')
        response = self.url_open('/my/tickets/%d' % self.ticket_b.id)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'HTTP ticket B', response.content)

    def test_portal_ticket_list_loads(self):
        self.authenticate('http_portal_a@example.com', 'demo12345')
        response = self.url_open('/my/tickets')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'HTTP ticket A', response.content)
        self.assertNotIn(b'HTTP ticket B', response.content)

    def test_new_ticket_form_creates_a_ticket_owned_by_the_submitter(self):
        self.authenticate('http_portal_a@example.com', 'demo12345')
        get_response = self.url_open('/my/tickets/new')
        token_match = re.search(
            rb'name="csrf_token" value="([^"]+)"', get_response.content)
        self.assertTrue(
            token_match, "Could not find a CSRF token on the new-ticket form")

        before = self.env['fmes.support.ticket'].search_count(
            [('partner_id', '=', self.partner_a.id)])
        self.url_open('/my/tickets/new', data={
            'csrf_token': token_match.group(1).decode(),
            'subject': 'Freshly submitted issue',
            'category': 'quality',
            'description': 'Created via the HTTP test.',
        })
        after = self.env['fmes.support.ticket'].search_count(
            [('partner_id', '=', self.partner_a.id)])
        self.assertEqual(after, before + 1)

    def test_portal_login_does_not_reach_the_backend(self):
        self.authenticate('http_portal_a@example.com', 'demo12345')
        response = self.url_open('/odoo')
        # A portal user hitting the backend root is redirected to /my, not
        # served the webclient (docs/04 security checklist T5).
        self.assertTrue(
            response.url.endswith('/my') or '/my' in response.url,
            "Expected a portal user to be redirected to /my, landed on %s"
            % response.url)
