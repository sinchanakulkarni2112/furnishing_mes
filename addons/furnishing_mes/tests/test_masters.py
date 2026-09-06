# -*- coding: utf-8 -*-
"""Phase 2 tests: shifts, the machine bridge, and the capacity matrix.

The capacity resolution tests are the important ones. Automated planning is
only as good as the rate it resolves, and a silently wrong rate produces plans
that look plausible and are not.
"""

from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError, AccessError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import FmesTestCase


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase2')
class TestShift(FmesTestCase):

    def test_day_shift_hours(self):
        """06:00-14:00 with a 30 minute break is 8 hours gross, 7.5 net."""
        self.assertEqual(self.shift_a.duration_hours, 8.0)
        self.assertEqual(self.shift_a.net_hours, 7.5)
        self.assertFalse(self.shift_a.crosses_midnight)

    def test_night_shift_wraps_past_midnight(self):
        """22:00-06:00 is 8 hours, not minus 16 (assumption A1, shift C)."""
        self.assertTrue(self.shift_c.crosses_midnight)
        self.assertEqual(self.shift_c.duration_hours, 8.0)
        self.assertEqual(self.shift_c.net_hours, 7.5)

    def test_net_hours_follow_the_break(self):
        self.shift_a.break_minutes = 60
        self.assertEqual(self.shift_a.net_hours, 7.0)

    def test_time_range_is_readable(self):
        self.assertEqual(self.shift_a.time_range, '06:00 - 14:00')
        self.assertEqual(self.shift_c.time_range, '22:00 - 06:00 (+1d)')

    def test_half_hour_start_renders_correctly(self):
        shift = self.env['fmes.shift'].create({
            'name': 'Half Past', 'code': 'HP',
            'start_time': 6.5, 'end_time': 14.5, 'break_minutes': 0,
        })
        self.assertEqual(shift.time_range, '06:30 - 14:30')

    def test_identical_start_and_end_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['fmes.shift'].create({
                'name': 'Zero', 'code': 'ZR',
                'start_time': 8.0, 'end_time': 8.0,
            })

    def test_time_outside_the_clock_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['fmes.shift'].create({
                'name': 'Bad', 'code': 'BD',
                'start_time': 25.0, 'end_time': 8.0,
            })

    def test_break_longer_than_shift_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['fmes.shift'].create({
                'name': 'All Break', 'code': 'AB',
                'start_time': 6.0, 'end_time': 8.0,
                'break_minutes': 180,
            })

    @mute_logger('odoo.sql_db')
    def test_shift_code_is_unique_per_company(self):
        with self.assertRaises(IntegrityError):
            self.env['fmes.shift'].create({
                'name': 'Duplicate', 'code': 'TA',
                'start_time': 6.0, 'end_time': 14.0,
            })
            self.env.flush_all()


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase2')
class TestMachineEquipmentBridge(FmesTestCase):
    """Gap G3: the link Odoo Enterprise provides through mrp_maintenance."""

    def test_link_from_the_machine_propagates_to_equipment(self):
        self.assertEqual(self.equipment_saw.workcenter_id, self.wc_saw)

    def test_link_from_the_equipment_propagates_to_the_machine(self):
        self.equipment_edge.workcenter_id = self.wc_edge.id
        self.assertEqual(self.wc_edge.equipment_id, self.equipment_edge)

    def test_reassigning_detaches_the_previous_equipment(self):
        spare = self.env['maintenance.equipment'].create({'name': 'Spare Saw'})
        self.wc_saw.equipment_id = spare.id
        self.assertEqual(spare.workcenter_id, self.wc_saw)
        self.assertFalse(
            self.equipment_saw.workcenter_id,
            "The previously linked equipment should have been detached")

    def test_clearing_the_link_clears_both_sides(self):
        self.wc_saw.equipment_id = False
        self.assertFalse(self.equipment_saw.workcenter_id)

    def test_department_flows_through_to_equipment(self):
        self.assertEqual(
            self.equipment_saw.fmes_department_id, self.dept_cutting)

    @mute_logger('odoo.sql_db')
    def test_equipment_cannot_serve_two_machines(self):
        with self.assertRaises(IntegrityError):
            self.wc_edge.equipment_id = self.equipment_saw.id
            self.env.flush_all()


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase2')
class TestCapacityMatrix(FmesTestCase):

    # -------------------------------------------------- normalisation
    def test_hourly_rate_passes_through(self):
        self.assertEqual(self.cap_product.std_output_per_hour, 48.0)

    def test_per_shift_rate_is_normalised_to_hours(self):
        """60 units per 7.5-hour shift is 8 per hour."""
        row = self.env['fmes.capacity.matrix'].create({
            'workcenter_id': self.wc_edge.id,
            'product_id': self.product_wardrobe.id,
            'std_output_qty': 60.0,
            'time_basis': 'per_shift',
            'basis_hours': 7.5,
        })
        self.assertEqual(row.std_output_per_hour, 8.0)

    def test_efficiency_factor_derates_the_effective_rate(self):
        row = self.env['fmes.capacity.matrix'].create({
            'workcenter_id': self.wc_spray.id,
            'product_id': self.product_wardrobe.id,
            'std_output_qty': 10.0,
            'time_basis': 'per_hour',
            'basis_hours': 1.0,
            'efficiency_factor': 0.85,
        })
        self.assertEqual(row.std_output_per_hour, 10.0)
        self.assertEqual(row.effective_output_per_hour, 8.5)

    def test_scope_is_derived(self):
        self.assertEqual(self.cap_product.scope, 'product')
        self.assertEqual(self.cap_category_parent.scope, 'category')

    # ---------------------------------------------------- resolution
    def test_exact_product_rate_wins_over_the_category(self):
        row = self.env['fmes.capacity.matrix']._resolve(
            self.wc_saw, self.product_panel)
        self.assertEqual(row, self.cap_product)
        self.assertEqual(row.std_output_per_hour, 48.0)

    def test_falls_back_to_the_parent_category(self):
        """The rate sits on the parent category; the product is two levels down."""
        row = self.env['fmes.capacity.matrix']._resolve(
            self.wc_saw, self.product_wardrobe)
        self.assertEqual(
            row, self.cap_category_parent,
            "Resolution must walk up the product category tree")

    def test_resolves_a_product_on_the_category_itself(self):
        row = self.env['fmes.capacity.matrix']._resolve(
            self.wc_saw, self.product_desk)
        self.assertEqual(row, self.cap_category_parent)

    def test_unrated_product_resolves_to_nothing(self):
        row = self.env['fmes.capacity.matrix']._resolve(
            self.wc_spray, self.product_unrated)
        self.assertFalse(row)

    def test_missing_rate_reports_zero_rather_than_guessing(self):
        """A missing rate must be visible, not silently substituted.

        Returning the work center's default_capacity here would produce
        plausible-looking plans built on an unrelated number.
        """
        self.wc_spray.default_capacity = 99.0
        rate = self.wc_spray.fmes_get_output_rate(self.product_unrated)
        self.assertEqual(rate, 0.0)

    def test_rate_helper_applies_the_efficiency_factor(self):
        self.cap_product.efficiency_factor = 0.5
        self.assertEqual(
            self.wc_saw.fmes_get_output_rate(self.product_panel), 24.0)

    def test_expired_rate_is_not_resolved(self):
        self.cap_product.date_to = '2020-12-31'
        row = self.env['fmes.capacity.matrix']._resolve(
            self.wc_saw, self.product_panel, date='2026-01-05')
        self.assertEqual(
            row, self.cap_category_parent,
            "An expired product rate should fall through to the category")

    def test_rate_valid_on_the_requested_date_is_used(self):
        self.cap_product.date_from = '2026-01-01'
        self.cap_product.date_to = '2026-12-31'
        row = self.env['fmes.capacity.matrix']._resolve(
            self.wc_saw, self.product_panel, date='2026-06-01')
        self.assertEqual(row, self.cap_product)

    def test_resolution_is_scoped_to_the_machine(self):
        row = self.env['fmes.capacity.matrix']._resolve(
            self.wc_spray, self.product_panel)
        self.assertFalse(
            row, "A rate on one machine must not leak to another")

    # --------------------------------------------------- constraints
    def test_overlapping_validity_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['fmes.capacity.matrix'].create({
                'workcenter_id': self.wc_saw.id,
                'product_id': self.product_panel.id,
                'std_output_qty': 30.0,
            })

    def test_non_overlapping_validity_is_allowed(self):
        self.cap_product.date_to = '2026-06-30'
        later = self.env['fmes.capacity.matrix'].create({
            'workcenter_id': self.wc_saw.id,
            'product_id': self.product_panel.id,
            'std_output_qty': 55.0,
            'date_from': '2026-07-01',
        })
        self.assertTrue(later)

    @mute_logger('odoo.sql_db')
    def test_row_without_a_target_is_rejected(self):
        """Enforced by a database CHECK.

        Odoo inserts the row before running Python constraints, so the SQL
        constraint is what actually catches this. Odoo still surfaces the
        friendly message declared alongside it.
        """
        with self.assertRaises(IntegrityError):
            self.env['fmes.capacity.matrix'].create({
                'workcenter_id': self.wc_saw.id,
                'std_output_qty': 10.0,
            })
            self.env.flush_all()

    def test_valid_from_after_valid_to_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['fmes.capacity.matrix'].create({
                'workcenter_id': self.wc_edge.id,
                'product_id': self.product_desk.id,
                'std_output_qty': 10.0,
                'date_from': '2026-12-01',
                'date_to': '2026-01-01',
            })

    @mute_logger('odoo.sql_db')
    def test_zero_output_is_rejected(self):
        with self.assertRaises(IntegrityError):
            self.env['fmes.capacity.matrix'].create({
                'workcenter_id': self.wc_edge.id,
                'product_id': self.product_desk.id,
                'std_output_qty': 0.0,
            })
            self.env.flush_all()

    # ------------------------------------------------------ manpower
    def test_manpower_prefers_the_capacity_row(self):
        self.assertEqual(
            self.wc_saw.fmes_get_std_manpower(self.product_panel), 1.0)

    def test_manpower_falls_back_to_the_machine(self):
        self.assertEqual(
            self.wc_saw.fmes_get_std_manpower(self.product_unrated), 2.0)

    def test_capacity_count_on_the_machine(self):
        self.assertEqual(self.wc_saw.fmes_capacity_count, 2)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase2')
class TestLossReasons(FmesTestCase):
    """Requirement 6.1 taxonomy, layered on Odoo's own loss reasons."""

    def test_every_category_has_at_least_one_reason(self):
        from odoo.addons.furnishing_mes.models\
            .mrp_workcenter_productivity_loss import FMES_LOSS_CATEGORY
        Loss = self.env['mrp.workcenter.productivity.loss']
        missing = [
            key for key, _label in FMES_LOSS_CATEGORY
            if not Loss.search_count([('fmes_category', '=', key)])
        ]
        self.assertFalse(
            missing, "No downtime reason seeded for: %s" % missing)

    def test_odoo_effectiveness_category_is_preserved(self):
        """OEE depends on loss_type; our category must not have replaced it."""
        reason = self.env.ref('mrp.block_reason1')
        self.assertEqual(reason.fmes_category, 'maintenance')
        self.assertEqual(
            reason.loss_type, 'availability',
            "Odoo's own loss_type must survive, or _compute_oee breaks")

    def test_breakdown_reason_escalates_to_maintenance(self):
        self.assertTrue(
            self.env.ref('mrp.block_reason1').fmes_requires_maintenance)

    def test_planned_stoppages_are_flagged(self):
        self.assertTrue(
            self.env.ref('furnishing_mes.loss_planned_maintenance')
            .fmes_is_planned)
        self.assertTrue(self.env.ref('mrp.block_reason2').fmes_is_planned)

    def test_productive_time_is_not_a_loss_category(self):
        self.assertFalse(
            self.env.ref('mrp.block_reason7').fmes_category,
            "Fully Productive Time is not a loss and must stay uncategorised")


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase2')
class TestSequences(FmesTestCase):

    def test_all_document_sequences_exist(self):
        codes = [
            'fmes.production.plan', 'fmes.production.entry',
            'fmes.maintenance.schedule', 'fmes.support.ticket',
            'fmes.import.batch',
        ]
        for code in codes:
            self.assertTrue(
                self.env['ir.sequence'].search_count([('code', '=', code)]),
                "Missing sequence %s" % code)

    def test_plan_sequence_produces_the_documented_format(self):
        number = self.env['ir.sequence'].next_by_code('fmes.production.plan')
        self.assertTrue(number.startswith('PLAN/'), number)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase2')
class TestMasterDataAccess(FmesTestCase):
    """The permission matrix in docs/04-security-model.md, for Phase 2 models."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = cls._create_user(
            'fmes_operator_p2', 'furnishing_mes.group_fmes_operator')
        cls.supervisor = cls._create_user(
            'fmes_supervisor_p2', 'furnishing_mes.group_fmes_supervisor')
        cls.manager = cls._create_user(
            'fmes_manager_p2', 'furnishing_mes.group_fmes_manager')

    def test_operator_may_read_shifts(self):
        shift = self.shift_a.with_user(self.operator)
        self.assertTrue(shift.name)

    def test_operator_may_not_change_shifts(self):
        with self.assertRaises(AccessError):
            self.shift_a.with_user(self.operator).write({'break_minutes': 45})

    def test_operator_may_not_read_the_capacity_matrix(self):
        with self.assertRaises(AccessError):
            self.cap_product.with_user(self.operator).read(['std_output_qty'])

    def test_supervisor_may_read_but_not_change_the_capacity_matrix(self):
        row = self.cap_product.with_user(self.supervisor)
        self.assertTrue(row.std_output_qty)
        with self.assertRaises(AccessError):
            row.write({'std_output_qty': 99.0})

    def test_manager_has_full_control(self):
        row = self.cap_product.with_user(self.manager)
        row.write({'std_output_qty': 50.0})
        self.assertEqual(row.std_output_qty, 50.0)
        self.shift_a.with_user(self.manager).write({'break_minutes': 45})

    def test_efficiency_factor_is_manager_only(self):
        """Field-level restriction is enforced server-side, not just hidden."""
        fields = self.env['fmes.capacity.matrix'].with_user(
            self.supervisor).fields_get()
        self.assertNotIn(
            'efficiency_factor', fields,
            "The efficiency factor must not be readable by a supervisor")
        self.assertIn(
            'efficiency_factor',
            self.env['fmes.capacity.matrix'].with_user(
                self.manager).fields_get())
