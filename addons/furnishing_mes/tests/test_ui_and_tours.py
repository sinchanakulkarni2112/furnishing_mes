# -*- coding: utf-8 -*-
"""UI, portal, systray and tour registration checks."""

import os

from odoo.tests.common import HttpCase
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestUiAndTours(HttpCase):
    """Non-browser verification of UI assets, tours, portal and systray."""

    def test_app_icon_is_configured_and_served_over_http(self):
        menu_root = self.env.ref('furnishing_mes.menu_fmes_root')
        self.assertEqual(
            menu_root.web_icon,
            'furnishing_mes,static/description/icon.png',
        )
        resp = self.url_open('/furnishing_mes/static/description/icon.png')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_three_owl_tours_are_bundled_in_backend_assets(self):
        base = os.path.dirname(__file__)
        manifest_path = os.path.join(base, '..', '__manifest__.py')
        with open(manifest_path, encoding='utf-8') as f:
            manifest = eval(f.read())
        backend_assets = manifest['assets'].get('web.assets_backend', [])
        tour_js_path = 'furnishing_mes/static/src/js/tours/fmes_tours.js'
        self.assertIn(tour_js_path, backend_assets)
        tour_file = os.path.join(base, '..', 'static', 'src', 'js', 'tours',
                                 'fmes_tours.js')
        with open(tour_file, encoding='utf-8') as f:
            tour_source = f.read()
        self.assertIn('fmes_shopfloor_terminal_tour', tour_source)
        self.assertIn('fmes_scheduling_board_tour', tour_source)
        self.assertIn('fmes_executive_dashboard_tour', tour_source)
        client_actions = self.env['ir.actions.client'].search([
            ('tag', 'in', [
                'fmes_shopfloor_terminal',
                'fmes_scheduling_board',
                'fmes_executive_dashboard',
            ])
        ])
        self.assertEqual(len(client_actions), 3)

    def test_alert_systray_unread_count_tracks_acknowledgement(self):
        alert_model = self.env['fmes.alert']
        rule = self.env['fmes.alert.rule'].search([], limit=1)
        self.assertTrue(rule)
        before = alert_model.get_unread_count()
        alert = alert_model.create({
            'rule_id': rule.id,
            'subject': 'Unit test alert',
            'body': '<p>test</p>',
            'severity': 'warning',
            'state': 'new',
        })
        self.assertEqual(alert_model.get_unread_count(), before + 1)
        alert.action_acknowledge()
        self.assertEqual(alert_model.get_unread_count(), before)

    def test_portal_pages_render_for_customer(self):
        portal_group = self.env.ref('base.group_portal')
        portal_user = self.env['res.users'].create({
            'name': 'Portal Test User',
            'login': 'portal_test_user',
            'password': 'portal_test_pw',
            'groups_id': [(6, 0, [portal_group.id])],
        })
        self.authenticate(portal_user.login, 'portal_test_pw')
        orders = self.url_open('/my/orders')
        self.assertEqual(orders.status_code, 200)
        production = self.url_open('/my/production-report')
        self.assertEqual(production.status_code, 200)
        tickets = self.url_open('/my/tickets')
        self.assertEqual(tickets.status_code, 200)
