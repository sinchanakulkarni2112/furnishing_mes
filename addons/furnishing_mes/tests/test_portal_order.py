# -*- coding: utf-8 -*-
"""Portal order → factory flow (portal order form, alert, planning, dashboard).

Three claims, checked in the order they can break:

1. The form is a locked-down door (real HTTP): an order is created for
   the LOGGED-IN customer no matter what else the POST body carries,
   price/discount client input is never read, and only genuinely
   orderable products and positive quantities are accepted.
2. The order reaches the factory's eventing (ORM): the flag the portal
   form stamps is exactly what the new-order-received automation filters
   on, and orders typed into the backend stay quiet.
3. The order reaches the factory's numbers (ORM): the planning engine's
   demand collector and the dashboard's live incoming-demand tile see
   the same open, uncovered, non-service demand — and neither leaks
   across companies, while still reaching a supervisor or operator who
   has no sale.order rights at all.
"""

import re
from datetime import date

from odoo.tests import HttpCase, tagged

from .test_portal import PortalCase

REFERENCE_DATE = '2026-01-05'


@tagged('post_install', '-at_install', 'fmes', 'fmes_portal_order')
class TestPortalOrderHttp(HttpCase):
    """Real HTTP requests — the only place controller-level input
    handling (or a controller-level ownership bug) can ever surface."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_a = cls.env['res.partner'].create({
            'name': 'Order Customer A', 'is_company': True,
            'customer_rank': 1})
        cls.user_a = cls.env['res.users'].create({
            'name': 'Order Contact A', 'login': 'order_portal_a@example.com',
            'email': 'order_portal_a@example.com', 'password': 'demo12345',
            'partner_id': cls.partner_a.id,
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })
        cls.partner_b = cls.env['res.partner'].create({
            'name': 'Order Customer B', 'is_company': True,
            'customer_rank': 1})
        cls.product = cls.env['product.product'].create({
            'name': 'Portal Orderable Wardrobe', 'list_price': 100.0})
        cls.service = cls.env['product.product'].create({
            'name': 'Portal Assembly Service', 'type': 'service'})
        cls.unsaleable = cls.env['product.product'].create({
            'name': 'Portal Internal Fixture', 'sale_ok': False})

    def _order_count(self):
        return self.env['sale.order'].search_count(
            [('partner_id', '=', self.partner_a.id)])

    def _submit(self, **extra):
        """GET the form, then POST it with `extra` overriding defaults."""
        self.authenticate('order_portal_a@example.com', 'demo12345')
        response = self.url_open('/my/orders/new')
        self.assertEqual(response.status_code, 200)
        token_match = re.search(
            rb'name="csrf_token" value="([^"]+)"', response.content)
        self.assertTrue(
            token_match, "Could not find a CSRF token on the order form")
        data = {
            'csrf_token': token_match.group(1).decode(),
            'product_id': str(self.product.id),
            'product_uom_qty': '5',
            'order_state': 'draft',
        }
        data.update(extra)
        return self.url_open('/my/orders/new', data=data)

    def _last_order(self):
        return self.env['sale.order'].search(
            [('partner_id', '=', self.partner_a.id)],
            order='id desc', limit=1)

    def test_form_lists_only_orderable_products(self):
        self.authenticate('order_portal_a@example.com', 'demo12345')
        response = self.url_open('/my/orders/new')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.product.name.encode(), response.content)
        self.assertNotIn(self.service.name.encode(), response.content)
        self.assertNotIn(self.unsaleable.name.encode(), response.content)

    def test_home_links_to_the_order_form(self):
        self.authenticate('order_portal_a@example.com', 'demo12345')
        response = self.url_open('/my/home')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'/my/orders/new', response.content)

    def test_order_is_pinned_to_the_logged_in_customer_and_priced_server_side(self):
        before = self._order_count()
        response = self._submit(
            # Everything a tampered client would try: order for someone
            # else, and set the price/discount themselves.
            partner_id=str(self.partner_b.id),
            price_unit='0.01',
            discount='90',
        )
        self.assertEqual(self._order_count(), before + 1)
        order = self._last_order()
        self.assertEqual(order.partner_id, self.partner_a)
        self.assertNotEqual(order.partner_id, self.partner_b)
        self.assertTrue(order.fmes_from_portal)
        line = order.order_line
        self.assertEqual(line.product_id, self.product)
        self.assertEqual(line.product_uom_qty, 5.0)
        # Pricelist compute, not the 0.01/90% the POST body asked for.
        self.assertEqual(line.price_unit, 100.0)
        self.assertEqual(line.discount, 0.0)
        # The created order must be openable by the customer who placed
        # it (subscribed follower — sale's portal rule reads followers).
        self.assertEqual(response.status_code, 200)
        self.assertIn(order.name.encode(), response.content)

    def test_unorderable_product_is_rejected(self):
        before = self._order_count()
        for product in (self.service, self.unsaleable):
            response = self._submit(product_id=str(product.id))
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'cannot be ordered', response.content)
        response = self._submit(product_id='999999')
        self.assertIn(b'cannot be ordered', response.content)
        self.assertEqual(self._order_count(), before)

    def test_bad_quantity_is_rejected(self):
        before = self._order_count()
        for raw in ('0', '-3', 'abc'):
            response = self._submit(product_uom_qty=raw)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Quantity must be greater than zero', response.content)
        self.assertEqual(self._order_count(), before)

    def test_confirm_submission_places_the_order(self):
        before = self._order_count()
        self._submit(order_state='confirmed')
        self.assertEqual(self._order_count(), before + 1)
        self.assertEqual(self._last_order().state, 'sale')


@tagged('post_install', '-at_install', 'fmes', 'fmes_portal_order')
class TestPortalOrderFactoryFlow(PortalCase):
    """Alert, planning collector and dashboard — the three factory-side
    surfaces a portal order has to reach. `PortalCase` supplies the two
    unrelated customers and their portal logins."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rule = cls.env.ref(
            'furnishing_mes.alert_rule_new_order_received')
        cls.service = cls.env['fmes.dashboard.service']
        # The tile is company-wide by design, so a demo dataset loaded in
        # the same database (which these tests never read) would sit under
        # every absolute figure. Measuring the floor once here keeps each
        # assertion a statement about THIS test's orders only.
        cls.baseline_demand = cls.service._incoming_demand(cls.company)

    @classmethod
    def _portal_order(cls, product, qty, **vals):
        """The shape `/my/orders/new` writes: flagged, confirmed, one line."""
        defaults = {
            'partner_id': cls.partner_a.id,
            'fmes_from_portal': True,
            'state': 'sale',
        }
        defaults.update(vals)
        order = cls.env['sale.order'].create(defaults)
        cls.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': product.id,
            'product_uom_qty': qty,
        })
        return order

    def _alerts_for(self, order):
        return self.env['fmes.alert'].search([
            ('rule_id', '=', self.rule.id),
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', order.id),
        ])

    # ------------------------------------------------------------- alert
    def test_portal_order_raises_new_order_received(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner_a.id, 'fmes_from_portal': True})
        alert = self._alerts_for(order)
        self.assertTrue(
            alert, "A portal-placed order must raise new_order_received")

    def test_backend_entered_order_stays_silent(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner_a.id})
        self.assertFalse(
            self._alerts_for(order),
            "The alert is scoped to orders the customer placed themselves")

    # ----------------------------------------------------------- planning
    def test_confirmed_portal_order_reaches_the_demand_collector(self):
        order = self._portal_order(self.product_wardrobe, 10.0)
        engine = self.env['fmes.planning.engine']

        collected = engine._collect_demand(
            date(2026, 1, 5), date(2026, 1, 7),
            demand_source='mo_and_so', company=self.company)
        mine = [d for d in collected if d['origin'] == order.name]
        self.assertTrue(
            mine, "A confirmed portal order must reach the planner")
        self.assertEqual(sum(d['qty'] for d in mine), 10.0)

        # ...but only when the generator is asked for sales orders: the
        # wizard's default stays `open_mo`, and this asserts the choice is
        # what admits SO demand, not an accident of the collector.
        collected = engine._collect_demand(
            date(2026, 1, 5), date(2026, 1, 7),
            demand_source='open_mo', company=self.company)
        self.assertNotIn(order.name, [d['origin'] for d in collected])

    # ---------------------------------------------------------- dashboard
    def test_open_portal_demand_appears_on_the_dashboard(self):
        self._portal_order(self.product_wardrobe, 10.0)
        self._portal_order(self.product_desk, 5.0)
        # A draft order is not committed demand yet.
        self._portal_order(self.product_panel, 99.0, state='draft')

        data = self.service.get_dashboard_data(
            REFERENCE_DATE, REFERENCE_DATE, company_id=self.company.id)
        tile = data['kpis']['incoming_demand_qty']
        self.assertAlmostEqual(
            tile['value'], round(self.baseline_demand + 15.0, 1), places=1)
        self.assertIsNone(tile['previous'])
        self.assertIsNone(tile['target'])

    def test_delivered_quantity_and_open_productions_are_excluded(self):
        partial = self._portal_order(self.product_wardrobe, 10.0)
        partial.order_line.qty_delivered = 4.0
        self._portal_order(self.product_desk, 8.0).order_line.qty_delivered = 8.0
        self._portal_order(self.product_panel, 50.0)
        covering_mo = self.env['mrp.production'].create({
            'product_id': self.product_panel.id, 'product_qty': 5.0,
        })
        self.assertIn(covering_mo.state, ('draft', 'confirmed', 'progress'))

        data = self.service.get_dashboard_data(
            REFERENCE_DATE, REFERENCE_DATE, company_id=self.company.id)
        self.assertAlmostEqual(
            data['kpis']['incoming_demand_qty']['value'],
            round(self.baseline_demand + 6.0, 1), places=1,
            msg="Delivered qty drops out line-by-line, and the 50 units of "
                "product_panel an open MO already covers are not incoming "
                "demand any more")

    def test_incoming_demand_is_company_scoped(self):
        other_company = self.env['res.company'].create(
            {'name': 'Other Factory Co'})
        self._portal_order(self.product_wardrobe, 7.0)
        self._portal_order(
            self.product_wardrobe, 3.0, company_id=other_company.id)

        mine = self.service.get_dashboard_data(
            REFERENCE_DATE, REFERENCE_DATE, company_id=self.company.id)
        self.assertAlmostEqual(
            mine['kpis']['incoming_demand_qty']['value'],
            round(self.baseline_demand + 7.0, 1), places=1)
        # The fresh company has no demo floor of its own.
        theirs = self.service.get_dashboard_data(
            REFERENCE_DATE, REFERENCE_DATE, company_id=other_company.id)
        self.assertEqual(
            theirs['kpis']['incoming_demand_qty']['value'], 3.0)

    def test_supervisors_and_operators_reach_the_tile_despite_missing_sale_acl(self):
        self._portal_order(self.product_wardrobe, 10.0)
        supervisor = self._create_user(
            'fmes_portal_order_sup', 'furnishing_mes.group_fmes_supervisor')
        # Assigned to a department the demand has nothing to do with:
        # incoming demand is unassigned by definition (no MO exists to
        # name a department), which the rules keep visible.
        supervisor.fmes_department_ids = [(6, 0, [self.dept_finishing.id])]
        operator = self._create_user(
            'fmes_portal_order_op', 'furnishing_mes.group_fmes_operator')

        # Neither role can read sale.order.line natively — the tile must
        # still come back, at the same figure, for every scope.
        for user in (supervisor, operator):
            self.assertAlmostEqual(
                self.service.with_user(user)._incoming_demand(self.company),
                self.baseline_demand + 10.0, places=3)

    def test_supervisor_read_carries_no_foreign_company_demand(self):
        other_company = self.env['res.company'].create(
            {'name': 'Scoped Other Co'})
        self._portal_order(
            self.product_wardrobe, 4.0, company_id=other_company.id)
        supervisor = self._create_user(
            'fmes_portal_order_sup2', 'furnishing_mes.group_fmes_supervisor')
        self.assertAlmostEqual(
            self.service.with_user(supervisor)._incoming_demand(self.company),
            self.baseline_demand, places=3,
            msg="Nothing of the other company's order may leak in")
