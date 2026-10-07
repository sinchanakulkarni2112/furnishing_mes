# -*- coding: utf-8 -*-
"""UI, portal, systray and tour registration checks."""

import os

from lxml import etree

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

    def test_top_level_tabs_open_the_tile_dashboard(self):
        """Each child tab of the app menu opens the dashboard, the app menu
        itself stays actionless, and Support Tickets keeps its own action."""
        action = self.env.ref('furnishing_mes.action_fmes_menu_dashboard')
        self.assertEqual(action._name, 'ir.actions.client')
        self.assertEqual(action.tag, 'fmes_menu_dashboard')

        root = self.env.ref('furnishing_mes.menu_fmes_root')
        self.assertFalse(
            root.action,
            "the app menu must stay actionless so it never overrides Odoo's "
            "derived app action",
        )

        tab_xmlids = [
            'menu_fmes_planning',
            'menu_fmes_dashboard',
            'menu_fmes_backlog',
            'menu_fmes_downtime',
            'menu_fmes_maintenance',
            'menu_fmes_inventory',
            'menu_fmes_reports',
            'menu_fmes_alerts',
            'menu_fmes_configuration',
        ]
        for xmlid in tab_xmlids:
            tab = self.env.ref('furnishing_mes.%s' % xmlid)
            self.assertEqual(
                tab.action, action,
                "%s should open the tile dashboard" % xmlid,
            )
            self.assertEqual(tab.action._name, 'ir.actions.client')

        support = self.env.ref('furnishing_mes.menu_fmes_support_tickets')
        self.assertEqual(
            support.action._name, 'ir.actions.act_window',
            "Support Tickets has no children to show, so it keeps its own action",
        )

        # What the app tile opens is Odoo's derived app action: the action of
        # the app's first visible child, which is now the dashboard.
        web_menus = self.env['ir.ui.menu'].load_web_menus(False)
        self.assertEqual(web_menus[root.id]['actionID'], action.id)
        self.assertEqual(web_menus[root.id]['actionModel'], 'ir.actions.client')

    def test_dashboard_templates_extend_the_core_navbar(self):
        """The core navbar templates we extend exist, and every xpath in our
        extension blocks matches at least one node of them. The SectionsMenu
        extension is also the one that hides the tab bar while this app is on
        show, so assert the guard is on the sections container itself (the
        node carrying t-ref="appSubMenus") and not on an inner dropdown."""
        import odoo.addons.web as web_addon

        navbar_path = os.path.join(
            os.path.dirname(web_addon.__file__),
            'static', 'src', 'webclient', 'navbar', 'navbar.xml',
        )
        self.assertTrue(os.path.exists(navbar_path))
        core = etree.parse(navbar_path).getroot()
        core_names = {
            el.get('t-name') for el in core.iter() if el.get('t-name')
        }

        addon_path = os.path.join(
            os.path.dirname(__file__), '..', 'static', 'src', 'xml',
            'menu_dashboard.xml',
        )
        our_templates = etree.parse(addon_path).getroot()
        extensions = [
            el for el in our_templates
            if isinstance(el.tag, str) and el.get('t-inherit')
        ]
        self.assertEqual(len(extensions), 2)
        for extension in extensions:
            self.assertEqual(extension.get('t-inherit-mode'), 'extension')
            parent = extension.get('t-inherit')
            self.assertIn(parent, core_names)
            xpaths = extension.findall('xpath')
            self.assertTrue(xpaths, "%s extends nothing" % parent)
            for xpath in xpaths:
                self.assertTrue(
                    core.xpath(xpath.get('expr')),
                    "%s has no node matching %s"
                    % (parent, xpath.get('expr')),
                )

        sections = [
            el for el in extensions
            if el.get('t-inherit') == 'web.NavBar.SectionsMenu'
        ]
        self.assertEqual(len(sections), 1)
        guard = sections[0].findall('xpath')[0]
        self.assertEqual(guard.get('position'), 'attributes')
        self.assertIn('t-ref=\'appSubMenus\'', guard.get('expr'))
        attribute = guard.find('attribute')
        self.assertIsNotNone(attribute)
        self.assertEqual(attribute.get('name'), 't-if')
        self.assertIn('isFmesApp', attribute.text)

    def test_menu_dashboard_assets_are_registered_and_compile(self):
        """The dashboard's js, xml and scss are part of web.assets_backend,
        its data file loads after the menus it edits, and the bundle really
        compiles: our templates are registered, our extensions point at core
        templates, and the scss produced no error block."""
        base = os.path.dirname(__file__)
        with open(os.path.join(base, '..', '__manifest__.py'),
                  encoding='utf-8') as f:
            manifest = eval(f.read())

        backend_assets = manifest['assets'].get('web.assets_backend', [])
        for asset in (
            'furnishing_mes/static/src/js/menu_dashboard.js',
            'furnishing_mes/static/src/xml/menu_dashboard.xml',
            'furnishing_mes/static/src/scss/menu_dashboard.scss',
        ):
            self.assertIn(asset, backend_assets)

        data_files = manifest['data']
        self.assertIn('views/fmes_menus.xml', data_files)
        self.assertLess(
            data_files.index('views/menus.xml'),
            data_files.index('views/fmes_menus.xml'),
            "the dashboard action must be declared after the menus it is "
            "assigned to",
        )

        bundle = self.env['ir.qweb']._get_asset_bundle(
            'web.assets_backend', css=True, js=True,
        )
        js = self._bundle_text(bundle.js())
        for marker in (
            'registerTemplate("furnishing_mes.MenuDashboard"',
            'registerTemplateExtension("web.NavBar.SectionsMenu"',
            'registerTemplateExtension("web.SectionMenu"',
            '"fmes_menu_dashboard"',
        ):
            self.assertIn(marker, js)

        css = self._bundle_text(bundle.css())
        self.assertNotIn(
            'CSS error message', css,
            "the SCSS bundle failed to compile, see the css error block",
        )
        self.assertIn('o_fmes_menu_dashboard', css)

    def _bundle_text(self, asset):
        """bundle.js()/bundle.css() hand back an ir.attachment record, or the
        list of records they found for the bundle."""
        if isinstance(asset, int):
            asset = self.env['ir.attachment'].browse(asset)
        self.assertTrue(asset, "the bundle produced no attachment")
        content = asset[0].raw
        self.assertTrue(content, "the bundle attachment is empty")
        return content.decode('utf-8')
