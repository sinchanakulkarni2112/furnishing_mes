# -*- coding: utf-8 -*-
"""Shared test fixtures.

Builds a small, deterministic plant that every phase's tests can rely on.
Tests never read the demo dataset: demo data is there to make the system
demonstrable, and letting tests depend on it would make them fail the moment
someone tunes a demo figure.

Dates are fixed rather than relative to "today", so results are stable.
"""

from odoo.tests.common import TransactionCase

# A fixed Monday, so weekday-sensitive logic in later phases is deterministic.
REFERENCE_DATE = '2026-01-05'


class FmesTestCase(TransactionCase):
    """A two-department, three-machine, three-shift plant."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.reference_date = REFERENCE_DATE

        # ---------------------------------------------------------- shifts
        Shift = cls.env['fmes.shift']
        cls.shift_a = Shift.create({
            'name': 'Test Shift A', 'code': 'TA', 'sequence': 10,
            'start_time': 6.0, 'end_time': 14.0, 'break_minutes': 30,
        })
        cls.shift_b = Shift.create({
            'name': 'Test Shift B', 'code': 'TB', 'sequence': 20,
            'start_time': 14.0, 'end_time': 22.0, 'break_minutes': 30,
        })
        # Night shift: wraps past midnight, which is the interesting case.
        cls.shift_c = Shift.create({
            'name': 'Test Shift C', 'code': 'TC', 'sequence': 30,
            'start_time': 22.0, 'end_time': 6.0, 'break_minutes': 30,
        })
        cls.shifts = cls.shift_a + cls.shift_b + cls.shift_c

        # ----------------------------------------------------- departments
        Department = cls.env['hr.department']
        cls.dept_cutting = Department.create({'name': 'Test Cutting'})
        cls.dept_finishing = Department.create({'name': 'Test Finishing'})

        # ------------------------------------------------------- equipment
        Equipment = cls.env['maintenance.equipment']
        cls.equipment_saw = Equipment.create({'name': 'Test Saw Equipment'})
        cls.equipment_edge = Equipment.create({'name': 'Test Edge Equipment'})

        # -------------------------------------------------------- machines
        Workcenter = cls.env['mrp.workcenter']
        cls.wc_saw = Workcenter.create({
            'name': 'Test Panel Saw', 'code': 'T-SAW',
            'fmes_machine_code': 'T-SAW-01',
            'department_id': cls.dept_cutting.id,
            'equipment_id': cls.equipment_saw.id,
            'fmes_std_manpower': 2.0,
            'fmes_criticality': 'high',
        })
        cls.wc_edge = Workcenter.create({
            'name': 'Test Edge Bander', 'code': 'T-EDGE',
            'fmes_machine_code': 'T-EDGE-01',
            'department_id': cls.dept_cutting.id,
            'fmes_std_manpower': 1.0,
        })
        cls.wc_spray = Workcenter.create({
            'name': 'Test Spray Booth', 'code': 'T-SPRAY',
            'fmes_machine_code': 'T-SPRAY-01',
            'department_id': cls.dept_finishing.id,
            'fmes_std_manpower': 2.0,
            'fmes_is_bottleneck': True,
            'fmes_criticality': 'critical',
        })
        cls.workcenters = cls.wc_saw + cls.wc_edge + cls.wc_spray

        # ------------------------------------------------- product catalog
        Category = cls.env['product.category']
        cls.categ_furniture = Category.create({'name': 'Test Furniture'})
        cls.categ_wardrobe = Category.create({
            'name': 'Test Wardrobes', 'parent_id': cls.categ_furniture.id})

        Product = cls.env['product.product']
        cls.product_wardrobe = Product.create({
            'name': 'Test 2-Door Wardrobe',
            'default_code': 'T-WD-2D',
            'categ_id': cls.categ_wardrobe.id,
        })
        cls.product_panel = Product.create({
            'name': 'Test Wardrobe Panel',
            'default_code': 'T-WD-PNL',
            'categ_id': cls.categ_wardrobe.id,
        })
        # Sits directly under the parent category, to test the category walk.
        cls.product_desk = Product.create({
            'name': 'Test Office Desk',
            'default_code': 'T-OF-DESK',
            'categ_id': cls.categ_furniture.id,
        })
        # Deliberately has no capacity row anywhere.
        cls.product_unrated = Product.create({
            'name': 'Test Unrated Item',
            'default_code': 'T-UNRATED',
            'categ_id': cls.categ_wardrobe.id,
        })

        # ------------------------------------------------- capacity matrix
        Capacity = cls.env['fmes.capacity.matrix']
        # Category rate on the parent, so the walk-up is exercised.
        cls.cap_category_parent = Capacity.create({
            'workcenter_id': cls.wc_saw.id,
            'product_category_id': cls.categ_furniture.id,
            'std_output_qty': 10.0,
            'time_basis': 'per_hour',
            'basis_hours': 1.0,
            'std_manpower': 2.0,
        })
        # Product rate that must win over the category.
        cls.cap_product = Capacity.create({
            'workcenter_id': cls.wc_saw.id,
            'product_id': cls.product_panel.id,
            'std_output_qty': 48.0,
            'time_basis': 'per_hour',
            'basis_hours': 1.0,
            'std_manpower': 1.0,
            'priority': 1,
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @classmethod
    def _create_user(cls, login, group_xmlid):
        """Create an internal user in exactly one MES group."""
        return cls.env['res.users'].create({
            'name': login,
            'login': login,
            'email': '%s@example.com' % login,
            'groups_id': [(6, 0, [cls.env.ref(group_xmlid).id])],
        })
