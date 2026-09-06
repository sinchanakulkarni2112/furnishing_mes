# -*- coding: utf-8 -*-
"""Phase 1 smoke tests.

Verifies that the module installs, that the four-tier role hierarchy exists
with the correct implications, that the dormant ERP integration seam is
registered, and that the menu structure is in place.
"""

from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase1')
class TestModuleInstall(TransactionCase):
    """The module is installable and its foundations are present."""

    def test_module_is_installed(self):
        module = self.env['ir.module.module'].search(
            [('name', '=', 'furnishing_mes')], limit=1)
        self.assertTrue(module, "furnishing_mes is not in the module list")
        self.assertEqual(
            module.state, 'installed',
            "furnishing_mes should be installed, found state %r" % module.state)

    def test_declared_dependencies_are_installed(self):
        """Every declared dependency exists in Odoo 18 Community and installed.

        Guards against depending on an Enterprise-only module, which would fail
        on the customer's Community deployment.
        """
        expected = [
            'mail', 'product', 'uom', 'stock', 'resource', 'mrp',
            'maintenance', 'hr', 'sale_management', 'portal',
            'base_automation', 'base_import', 'spreadsheet_dashboard',
        ]
        modules = self.env['ir.module.module'].search(
            [('name', 'in', expected)])
        found = set(modules.mapped('name'))
        self.assertFalse(
            set(expected) - found,
            "Declared dependencies missing from this Odoo installation: %s"
            % sorted(set(expected) - found))
        not_installed = modules.filtered(lambda m: m.state != 'installed')
        self.assertFalse(
            not_installed,
            "Dependencies not installed: %s" % not_installed.mapped('name'))


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase1')
class TestSecurityGroups(TransactionCase):
    """The four-tier role hierarchy from docs/04-security-model.md."""

    def setUp(self):
        super().setUp()
        self.operator = self.env.ref('furnishing_mes.group_fmes_operator')
        self.supervisor = self.env.ref('furnishing_mes.group_fmes_supervisor')
        self.manager = self.env.ref('furnishing_mes.group_fmes_manager')
        self.portal = self.env.ref('base.group_portal')

    def test_all_four_tiers_exist(self):
        for group in (self.operator, self.supervisor, self.manager, self.portal):
            self.assertTrue(group, "A role tier is missing")

    def test_groups_share_the_module_category(self):
        category = self.env.ref('furnishing_mes.module_category_furnishing_mes')
        for group in (self.operator, self.supervisor, self.manager):
            self.assertEqual(
                group.category_id, category,
                "%s should sit under the Furnishing MES category" % group.name)

    def test_operator_is_an_internal_user(self):
        self.assertIn(
            self.env.ref('base.group_user'), self.operator.implied_ids,
            "Operator must imply base.group_user to be an internal user")

    def test_hierarchy_is_cumulative(self):
        """Supervisor implies Operator; Plant Manager implies Supervisor."""
        self.assertIn(
            self.operator, self.supervisor.implied_ids,
            "Supervisor must imply Operator")
        self.assertIn(
            self.supervisor, self.manager.implied_ids,
            "Plant Manager must imply Supervisor")
        # Transitively, a Plant Manager holds every Operator right.
        self.assertIn(
            self.operator, self.manager.trans_implied_ids,
            "Plant Manager must transitively hold Operator rights")

    def test_supervisor_holds_manufacturing_and_maintenance_rights(self):
        implied = self.supervisor.trans_implied_ids
        self.assertIn(self.env.ref('mrp.group_mrp_user'), implied)
        self.assertIn(
            self.env.ref('maintenance.group_equipment_manager'), implied)

    def test_manager_holds_manufacturing_manager_rights(self):
        implied = self.manager.trans_implied_ids
        self.assertIn(self.env.ref('mrp.group_mrp_manager'), implied)
        self.assertIn(self.env.ref('stock.group_stock_manager'), implied)

    def test_portal_tier_is_not_internal(self):
        """A Customer must never gain internal-user rights."""
        self.assertNotIn(
            self.env.ref('base.group_user'), self.portal.trans_implied_ids,
            "The portal group must not imply internal access")

    def test_admin_is_a_plant_manager(self):
        admin = self.env.ref('base.user_admin')
        self.assertIn(
            admin, self.manager.users,
            "The admin user should be a Plant Manager after install")


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase1')
class TestErpSyncMixin(TransactionCase):
    """The ERP 10.8 integration seam is present but dormant."""

    def test_mixin_is_registered(self):
        self.assertIn(
            'fmes.erp.sync.mixin', self.env,
            "The ERP sync mixin is not registered")

    def test_mixin_is_abstract(self):
        mixin = self.env['fmes.erp.sync.mixin']
        self.assertTrue(
            mixin._abstract,
            "The ERP sync mixin must stay abstract until a connector is built")

    def test_mixin_exposes_the_agreed_fields(self):
        fields = self.env['fmes.erp.sync.mixin']._fields
        for name in ('erp_external_id', 'erp_source_system', 'erp_last_sync',
                     'erp_sync_state', 'erp_sync_message'):
            self.assertIn(
                name, fields,
                "The integration seam is missing %r; adding it later would "
                "require matching live records to the ERP by hand" % name)

    def test_mixin_is_not_yet_mixed_into_any_model(self):
        """ERP integration is deferred: nothing should inherit the seam yet."""
        inheriting = [
            name for name, model in self.env.registry.items()
            if name != 'fmes.erp.sync.mixin'
            and 'fmes.erp.sync.mixin' in getattr(model, '_inherit_module', ())
        ]
        self.assertFalse(
            inheriting,
            "ERP integration is deferred, but these models already mix in the "
            "seam: %s" % inheriting)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase1')
class TestMenuStructure(TransactionCase):
    """The menu skeleton later phases hang their items from."""

    def test_root_menu_exists(self):
        root = self.env.ref('furnishing_mes.menu_fmes_root')
        self.assertEqual(root.name, 'Furnishing MES')
        self.assertFalse(root.parent_id, "The root menu must be top level")

    def test_all_sections_are_declared(self):
        sections = [
            'menu_fmes_dashboard', 'menu_fmes_planning', 'menu_fmes_production',
            'menu_fmes_downtime', 'menu_fmes_maintenance', 'menu_fmes_manpower',
            'menu_fmes_backlog', 'menu_fmes_alerts', 'menu_fmes_reports',
            'menu_fmes_configuration',
        ]
        root = self.env.ref('furnishing_mes.menu_fmes_root')
        for xmlid in sections:
            menu = self.env.ref('furnishing_mes.%s' % xmlid)
            self.assertEqual(
                menu.parent_id, root,
                "%s should hang off the Furnishing MES root" % xmlid)

    def test_configuration_is_restricted_to_plant_manager(self):
        config = self.env.ref('furnishing_mes.menu_fmes_configuration')
        self.assertIn(
            self.env.ref('furnishing_mes.group_fmes_manager'),
            config.groups_id,
            "Configuration must be limited to the Plant Manager")

    def test_machines_action_points_at_work_centers(self):
        action = self.env.ref('furnishing_mes.action_fmes_workcenter')
        self.assertEqual(action.res_model, 'mrp.workcenter')


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase1')
class TestSecurityBaseline(TransactionCase):
    """Project rule: no model ships without an ACL.

    Trivially true in Phase 1 (no models yet), but the check is written now so
    that it fails loudly the moment a later phase adds a model and forgets the
    ir.model.access.csv row.
    """

    def test_every_fmes_model_has_an_acl(self):
        models = self.env['ir.model'].search([('model', '=like', 'fmes.%')])
        concrete = models.filtered(lambda m: m.transient is False)
        missing = []
        for model in concrete:
            if model.model in self.env and self.env[model.model]._abstract:
                continue
            acls = self.env['ir.model.access'].search_count(
                [('model_id', '=', model.id)])
            if not acls:
                missing.append(model.model)
        self.assertFalse(
            missing,
            "These models have no ir.model.access entry: %s" % missing)
