# -*- coding: utf-8 -*-
"""Phase 8 tests: manpower logging, operator allocation and their feedback
into the planning engine and operator scoping.

Three things matter most here. Shortage maths must be the same sum-then-
divide standard-vs-actual pattern as everywhere else in this module (D0.7).
`fmes.operator.allocation`'s uniqueness constraint is what makes the model
trustworthy as a roster — one employee cannot be double-booked. And it must
correctly become the operator record rule's live source, ahead of the
permanent assignment Phase 4 shipped, without breaking a plant that has not
started rostering yet.
"""

from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import FmesTestCase

REFERENCE_DATE = '2026-01-05'


class ManpowerCase(FmesTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create(
            {'name': 'Test Employee', 'department_id': cls.dept_cutting.id})
        cls.employee2 = cls.env['hr.employee'].create(
            {'name': 'Test Employee 2', 'department_id': cls.dept_cutting.id})


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase8')
class TestManpowerLog(ManpowerCase):

    def test_shortage_maths(self):
        log = self.env['fmes.manpower.log'].create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'department_id': self.dept_cutting.id,
            'std_manpower': 5.0, 'actual_manpower': 3.0,
        })
        self.assertEqual(log.shortage, 2.0)
        self.assertAlmostEqual(log.shortage_pct, 40.0, places=4)
        self.assertAlmostEqual(log.utilization_pct, 60.0, places=4)

    def test_overstaffed_shortage_is_negative(self):
        log = self.env['fmes.manpower.log'].create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'department_id': self.dept_cutting.id,
            'std_manpower': 2.0, 'actual_manpower': 3.0,
        })
        self.assertEqual(log.shortage, -1.0)
        self.assertAlmostEqual(log.utilization_pct, 150.0, places=4)

    def test_zero_standard_guards_the_division(self):
        log = self.env['fmes.manpower.log'].create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'department_id': self.dept_cutting.id,
            'std_manpower': 0.0, 'actual_manpower': 2.0,
        })
        self.assertEqual(log.shortage_pct, 0.0)
        self.assertEqual(log.utilization_pct, 0.0)

    def test_onchange_workcenter_defaults_department_and_standard(self):
        log = self.env['fmes.manpower.log'].new({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'workcenter_id': self.wc_saw.id,
        })
        log._onchange_workcenter_id()
        self.assertEqual(log.department_id, self.dept_cutting)
        self.assertEqual(log.std_manpower, self.wc_saw.fmes_std_manpower)

    def test_onchange_department_sums_its_machines(self):
        log = self.env['fmes.manpower.log'].new({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'department_id': self.dept_cutting.id,
        })
        log._onchange_department_id()
        expected = self.wc_saw.fmes_std_manpower + self.wc_edge.fmes_std_manpower
        self.assertAlmostEqual(log.std_manpower, expected, places=4)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase8')
class TestOperatorAllocation(ManpowerCase):

    @mute_logger('odoo.sql_db')
    def test_one_allocation_per_employee_per_shift_per_day(self):
        self.env['fmes.operator.allocation'].create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'employee_id': self.employee.id, 'workcenter_id': self.wc_saw.id,
        })
        with self.assertRaises(IntegrityError):
            self.env['fmes.operator.allocation'].create({
                'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
                'employee_id': self.employee.id,
                'workcenter_id': self.wc_edge.id,
            })
            self.env.flush_all()

    def test_a_different_shift_or_day_is_not_a_duplicate(self):
        Allocation = self.env['fmes.operator.allocation']
        Allocation.create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'employee_id': self.employee.id, 'workcenter_id': self.wc_saw.id,
        })
        other_shift = Allocation.create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_b.id,
            'employee_id': self.employee.id, 'workcenter_id': self.wc_saw.id,
        })
        self.assertTrue(other_shift.exists())

    def test_department_is_derived_from_the_machine(self):
        row = self.env['fmes.operator.allocation'].create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'employee_id': self.employee.id, 'workcenter_id': self.wc_spray.id,
        })
        self.assertEqual(row.department_id, self.dept_finishing)

    def test_onchange_shift_defaults_hours(self):
        row = self.env['fmes.operator.allocation'].new({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
        })
        row._onchange_shift_id()
        self.assertAlmostEqual(row.hours, self.shift_a.net_hours, places=4)

    def test_copy_to_next_week_creates_a_row_seven_days_later(self):
        row = self.env['fmes.operator.allocation'].create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'employee_id': self.employee.id, 'workcenter_id': self.wc_saw.id,
            'state': 'present',
        })
        row.action_copy_to_next_week()
        copies = self.env['fmes.operator.allocation'].search([
            ('employee_id', '=', self.employee.id),
            ('id', '!=', row.id),
        ])
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies.date, row.date + timedelta(days=7))
        self.assertEqual(copies.state, 'planned',
                         "A copied row starts fresh, not carrying last "
                         "week's attendance forward")

    def test_copy_to_next_week_skips_an_existing_target(self):
        Allocation = self.env['fmes.operator.allocation']
        row = Allocation.create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'employee_id': self.employee.id, 'workcenter_id': self.wc_saw.id,
        })
        target_date = row.date + timedelta(days=7)
        Allocation.create({
            'date': target_date, 'shift_id': self.shift_a.id,
            'employee_id': self.employee.id, 'workcenter_id': self.wc_edge.id,
        })
        row.action_copy_to_next_week()
        at_target = Allocation.search([
            ('date', '=', target_date), ('employee_id', '=', self.employee.id),
        ])
        self.assertEqual(len(at_target), 1,
                         "An existing target-week row must be left alone, "
                         "not duplicated")
        self.assertEqual(at_target.workcenter_id, self.wc_edge,
                         "The pre-existing row's own machine must survive")


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase8')
class TestAllowedWorkcenterScoping(ManpowerCase):
    """`res.users.fmes_allowed_workcenter_ids` priority: today's roster,
    then the permanent assignment, then the department fallback."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = cls._create_user(
            'fmes_mp_op', 'furnishing_mes.group_fmes_operator')
        cls.operator.fmes_workcenter_ids = [(6, 0, [cls.wc_edge.id])]
        cls.employee.user_id = cls.operator.id

    def _today_row(self, workcenter, state='present'):
        today = fields.Date.context_today(self.operator)
        return self.env['fmes.operator.allocation'].create({
            'date': today,
            'shift_id': self.shift_a.id,
            'employee_id': self.employee.id,
            'workcenter_id': workcenter.id,
            'state': state,
        })

    def test_todays_roster_takes_priority_over_permanent_assignment(self):
        self._today_row(self.wc_saw)
        self.operator.invalidate_recordset(['fmes_allowed_workcenter_ids'])
        self.assertEqual(self.operator.fmes_allowed_workcenter_ids, self.wc_saw)

    def test_absent_today_falls_back_to_the_permanent_assignment(self):
        self._today_row(self.wc_saw, state='absent')
        self.operator.invalidate_recordset(['fmes_allowed_workcenter_ids'])
        self.assertEqual(
            self.operator.fmes_allowed_workcenter_ids, self.wc_edge,
            "An absent-only roster must not leave the operator with zero "
            "machines when a permanent assignment exists")

    def test_planned_not_yet_present_still_counts(self):
        self._today_row(self.wc_saw, state='planned')
        self.operator.invalidate_recordset(['fmes_allowed_workcenter_ids'])
        self.assertEqual(self.operator.fmes_allowed_workcenter_ids, self.wc_saw)

    def test_permanent_assignment_used_with_no_roster_at_all(self):
        self.operator.invalidate_recordset(['fmes_allowed_workcenter_ids'])
        self.assertEqual(self.operator.fmes_allowed_workcenter_ids, self.wc_edge)

    def test_department_fallback_when_neither_source_applies(self):
        self.operator.fmes_workcenter_ids = [(5, 0, 0)]
        self.operator.fmes_department_ids = [(6, 0, [self.dept_cutting.id])]
        self.operator.invalidate_recordset(['fmes_allowed_workcenter_ids'])
        self.assertEqual(
            set(self.operator.fmes_allowed_workcenter_ids.ids),
            {self.wc_saw.id, self.wc_edge.id})


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase8')
class TestManpowerImpactReport(ManpowerCase):

    def test_shortage_and_achievement_aggregate_by_department_shift(self):
        self.env['fmes.manpower.log'].create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'department_id': self.dept_cutting.id,
            'std_manpower': 4.0, 'actual_manpower': 2.0,
        })
        entry = self.env['fmes.production.entry'].create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'workcenter_id': self.wc_saw.id,
            'product_id': self.product_wardrobe.id,
            'planned_qty': 100.0, 'actual_qty': 40.0,
        })
        entry.action_submit()
        supervisor = self._create_user(
            'fmes_mp_impact_sup', 'furnishing_mes.group_fmes_supervisor')
        entry.with_user(supervisor).action_approve()
        self.env.flush_all()

        row = self.env['fmes.manpower.impact.report'].search([
            ('department_id', '=', self.dept_cutting.id),
            ('date', '=', REFERENCE_DATE), ('shift_id', '=', self.shift_a.id),
        ])
        self.assertEqual(len(row), 1)
        self.assertAlmostEqual(row.shortage_pct, 50.0, places=4)
        self.assertTrue(row.has_planned_qty)
        self.assertAlmostEqual(row.achievement_pct, 40.0, places=4)

    def test_manpower_only_slot_has_no_planned_qty(self):
        self.env['fmes.manpower.log'].create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'department_id': self.dept_cutting.id,
            'std_manpower': 4.0, 'actual_manpower': 4.0,
        })
        self.env.flush_all()
        row = self.env['fmes.manpower.impact.report'].search([
            ('department_id', '=', self.dept_cutting.id),
            ('date', '=', REFERENCE_DATE), ('shift_id', '=', self.shift_a.id),
        ])
        self.assertEqual(len(row), 1)
        self.assertFalse(row.has_planned_qty)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase8')
class TestManpowerSecurity(ManpowerCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = cls._create_user(
            'fmes_mp_sec_op', 'furnishing_mes.group_fmes_operator')
        cls.employee.user_id = cls.operator.id

    def test_operator_cannot_read_manpower_log(self):
        with self.assertRaises(AccessError):
            self.env['fmes.manpower.log'].with_user(self.operator).search([])

    def test_operator_sees_only_their_own_allocation(self):
        Allocation = self.env['fmes.operator.allocation']
        own = Allocation.create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'employee_id': self.employee.id, 'workcenter_id': self.wc_saw.id,
        })
        someone_else = Allocation.create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'employee_id': self.employee2.id, 'workcenter_id': self.wc_edge.id,
        })
        visible = Allocation.with_user(self.operator).search([])
        self.assertIn(own, visible)
        self.assertNotIn(someone_else, visible)

    def test_operator_cannot_write_the_roster(self):
        row = self.env['fmes.operator.allocation'].create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'employee_id': self.employee.id, 'workcenter_id': self.wc_saw.id,
        })
        with self.assertRaises(AccessError):
            row.with_user(self.operator).write({'state': 'present'})

    def test_supervisor_with_assigned_department_is_scoped_to_it(self):
        supervisor = self._create_user(
            'fmes_mp_sec_sup', 'furnishing_mes.group_fmes_supervisor')
        supervisor.fmes_department_ids = [(6, 0, [self.dept_cutting.id])]
        cutting_log = self.env['fmes.manpower.log'].create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'department_id': self.dept_cutting.id,
            'std_manpower': 2.0, 'actual_manpower': 2.0,
        })
        finishing_log = self.env['fmes.manpower.log'].create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'department_id': self.dept_finishing.id,
            'std_manpower': 2.0, 'actual_manpower': 2.0,
        })
        visible = self.env['fmes.manpower.log'].with_user(
            supervisor).search([])
        self.assertIn(cutting_log, visible)
        self.assertNotIn(finishing_log, visible)

    def test_supervisor_with_no_assigned_department_sees_everything(self):
        supervisor = self._create_user(
            'fmes_mp_sec_sup2', 'furnishing_mes.group_fmes_supervisor')
        self.env['fmes.manpower.log'].create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'department_id': self.dept_finishing.id,
            'std_manpower': 2.0, 'actual_manpower': 2.0,
        })
        visible = self.env['fmes.manpower.log'].with_user(
            supervisor).search([('department_id', '=', self.dept_finishing.id)])
        self.assertTrue(visible)

    def test_manager_sees_every_department_even_when_supervisor_scoped(self):
        manager = self._create_user(
            'fmes_mp_sec_mgr', 'furnishing_mes.group_fmes_manager')
        self.env['fmes.manpower.log'].create({
            'date': REFERENCE_DATE, 'shift_id': self.shift_a.id,
            'department_id': self.dept_finishing.id,
            'std_manpower': 2.0, 'actual_manpower': 2.0,
        })
        visible = self.env['fmes.manpower.log'].with_user(
            manager).search([('department_id', '=', self.dept_finishing.id)])
        self.assertTrue(
            visible,
            "A Plant Manager must never be caught by the supervisor's own "
            "department-scoped rule just because the roles are cumulative")

    def test_operator_cannot_read_the_manpower_impact_report(self):
        with self.assertRaises(AccessError):
            self.env['fmes.manpower.impact.report'].with_user(
                self.operator).search([])
