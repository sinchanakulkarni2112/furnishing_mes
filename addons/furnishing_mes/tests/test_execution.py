# -*- coding: utf-8 -*-
"""Phase 4 tests: daily production entries, the terminal, and the importer.

Two things matter most here. Approved entries must be immutable, because a
report is only worth reading if the figures behind it cannot be quietly
restated. And an operator on a shared tablet must not be able to reach another
operator's work — the terminal runs on the least trustworthy client in the
building.
"""

import base64
import io
from datetime import date, timedelta

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import HttpCase
from odoo.tools import mute_logger

from .common import FmesTestCase

try:
    from openpyxl import Workbook
except ImportError:  # pragma: no cover
    Workbook = None


class ExecutionCase(FmesTestCase):
    """The fixture plant plus a released plan to report against."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.day = date(2026, 1, 5)

        # Demand for the planning engine to work with; without it the
        # generated plan is empty and the feedback tests have nothing to hang on.
        cls.mo = cls.env['mrp.production'].create({
            'product_id': cls.product_wardrobe.id,
            'product_qty': 60.0,
            'date_deadline': cls.day,
            'date_start': cls.day,
        })

        cls.entry = cls.env['fmes.production.entry'].create({
            'date': cls.day,
            'shift_id': cls.shift_a.id,
            'workcenter_id': cls.wc_saw.id,
            'product_id': cls.product_wardrobe.id,
            'planned_qty': 100.0,
        })

    @classmethod
    def _released_plan(cls):
        plan = cls.env['fmes.planning.engine'].generate(cls.day, cls.day)
        plan.action_confirm()
        plan.action_release()
        return plan


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase4')
class TestProductionEntry(ExecutionCase):

    def test_sequence_is_assigned(self):
        self.assertTrue(self.entry.name.startswith('PE/'), self.entry.name)

    def test_quantities_are_derived(self):
        self.entry.write({'actual_qty': 90.0, 'rejected_qty': 5.0})
        self.assertEqual(self.entry.ok_qty, 85.0)
        self.assertEqual(self.entry.variance_qty, -10.0)
        self.assertAlmostEqual(self.entry.achievement_pct, 90.0, places=4)
        self.assertTrue(self.entry.has_target)

    def test_no_target_is_not_zero_achievement(self):
        """'No target set' and 'produced nothing' must not look alike."""
        entry = self.env['fmes.production.entry'].create({
            'date': self.day,
            'shift_id': self.shift_b.id,
            'workcenter_id': self.wc_saw.id,
            'product_id': self.product_panel.id,
            'actual_qty': 20.0,
        })
        self.assertFalse(entry.has_target)
        self.assertEqual(entry.achievement_pct, 0.0)

    def test_available_hours_come_from_the_shift(self):
        self.assertAlmostEqual(self.entry.available_hours, 7.5, places=4)
        self.entry.run_hours = 6.0
        self.assertAlmostEqual(self.entry.utilization_pct, 80.0, places=4)

    def test_standard_output_uses_the_capacity_matrix(self):
        """The saw makes 10/hour of this item; 5 hours should be 50."""
        self.entry.write({'run_hours': 5.0, 'actual_qty': 40.0})
        self.assertAlmostEqual(self.entry.std_output_qty, 50.0, places=4)
        self.assertAlmostEqual(self.entry.efficiency_pct, 80.0, places=4)

    def test_manpower_shortage(self):
        self.entry.actual_manpower = 1.0
        self.assertAlmostEqual(self.entry.std_manpower, 2.0, places=4)
        self.assertAlmostEqual(self.entry.manpower_shortage, 1.0, places=4)

    def test_rejected_cannot_exceed_produced(self):
        with self.assertRaises(ValidationError):
            self.entry.write({'actual_qty': 10.0, 'rejected_qty': 11.0})

    def test_hours_cannot_exceed_the_shift(self):
        with self.assertRaises(ValidationError):
            self.entry.write({'run_hours': 7.0, 'downtime_hours': 4.0})

    @mute_logger('odoo.sql_db')
    def test_one_entry_per_slot(self):
        with self.assertRaises(IntegrityError):
            self.env['fmes.production.entry'].create({
                'date': self.day,
                'shift_id': self.shift_a.id,
                'workcenter_id': self.wc_saw.id,
                'product_id': self.product_wardrobe.id,
            })
            self.env.flush_all()

    @mute_logger('odoo.sql_db')
    def test_negative_quantity_rejected(self):
        with self.assertRaises(IntegrityError):
            self.env['fmes.production.entry'].create({
                'date': self.day + timedelta(days=1),
                'shift_id': self.shift_a.id,
                'workcenter_id': self.wc_saw.id,
                'product_id': self.product_wardrobe.id,
                'actual_qty': -5.0,
            })
            self.env.flush_all()


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase4')
class TestApprovalWorkflow(ExecutionCase):

    def test_submit_then_approve(self):
        self.entry.actual_qty = 80.0
        self.entry.action_submit()
        self.assertEqual(self.entry.state, 'submitted')
        self.assertEqual(self.entry.submitted_by, self.env.user)
        self.entry.action_approve()
        self.assertEqual(self.entry.state, 'approved')
        self.assertTrue(self.entry.approved_on)

    def test_empty_shift_cannot_be_submitted(self):
        with self.assertRaises(UserError):
            self.entry.action_submit()

    def test_downtime_only_shift_can_be_submitted(self):
        """A machine that was down all shift still has something to report."""
        self.entry.downtime_hours = 7.0
        self.entry.action_submit()
        self.assertEqual(self.entry.state, 'submitted')

    def test_approval_requires_submission(self):
        self.entry.actual_qty = 10.0
        with self.assertRaises(UserError):
            self.entry.action_approve()

    def test_rejected_entry_can_be_resubmitted(self):
        self.entry.actual_qty = 80.0
        self.entry.action_submit()
        self.entry.action_reject()
        self.assertEqual(self.entry.state, 'rejected')
        self.entry.action_submit()
        self.assertEqual(self.entry.state, 'submitted')

    def test_approved_figures_are_locked(self):
        """Requirement 3.4: history that can be edited is not history."""
        self.entry.actual_qty = 80.0
        self.entry.action_submit()
        self.entry.action_approve()

        supervisor = self._create_user(
            'fmes_sup_lock', 'furnishing_mes.group_fmes_supervisor')
        with self.assertRaises(AccessError):
            self.entry.with_user(supervisor).write({'actual_qty': 999.0})

    def test_notes_stay_editable_after_approval(self):
        """Correcting a comment is not restating what a shift produced."""
        self.entry.actual_qty = 80.0
        self.entry.action_submit()
        self.entry.action_approve()
        supervisor = self._create_user(
            'fmes_sup_note', 'furnishing_mes.group_fmes_supervisor')
        self.entry.with_user(supervisor).write({'note': 'checked'})
        self.assertEqual(self.entry.note, 'checked')

    def test_manager_can_reopen_an_approved_entry(self):
        self.entry.actual_qty = 80.0
        self.entry.action_submit()
        self.entry.action_approve()
        manager = self._create_user(
            'fmes_mgr_reopen', 'furnishing_mes.group_fmes_manager')
        self.entry.with_user(manager).action_reset_to_draft()
        self.assertEqual(self.entry.state, 'draft')

    def test_supervisor_cannot_reopen_an_approved_entry(self):
        self.entry.actual_qty = 80.0
        self.entry.action_submit()
        self.entry.action_approve()
        supervisor = self._create_user(
            'fmes_sup_reopen', 'furnishing_mes.group_fmes_supervisor')
        with self.assertRaises(AccessError):
            self.entry.with_user(supervisor).action_reset_to_draft()


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase4')
class TestPlanFeedback(ExecutionCase):
    """Approving an entry closes the loop with Phase 3's carry-forward."""

    def setUp(self):
        super().setUp()
        self.plan = self._released_plan()
        self.line = self.plan.line_ids.filtered(
            lambda l: l.workcenter_id == self.wc_saw)[:1]
        self.assertTrue(self.line, "The fixture plan should load the saw")

    def _entry_for_line(self, line):
        return self.env['fmes.production.entry'].create({
            'date': line.date,
            'shift_id': line.shift_id.id,
            'workcenter_id': line.workcenter_id.id,
            'product_id': line.product_id.id,
            'plan_line_id': line.id,
            'planned_qty': line.planned_qty,
        })

    def test_full_output_marks_the_plan_line_done(self):
        entry = self._entry_for_line(self.line)
        entry.actual_qty = self.line.planned_qty
        entry.action_submit()
        entry.action_approve()
        self.assertEqual(self.line.state, 'done')
        self.assertAlmostEqual(
            self.line.qty_done, self.line.planned_qty, places=4)
        self.assertAlmostEqual(self.line.remaining_qty, 0.0, places=4)

    def test_partial_output_marks_the_line_partial(self):
        entry = self._entry_for_line(self.line)
        entry.actual_qty = self.line.planned_qty / 2.0
        entry.action_submit()
        entry.action_approve()
        self.assertEqual(self.line.state, 'partial')
        self.assertAlmostEqual(
            self.line.remaining_qty, self.line.planned_qty / 2.0, places=4)

    def test_unapproved_output_does_not_reach_the_plan(self):
        """Only signed-off figures move the plan."""
        entry = self._entry_for_line(self.line)
        entry.actual_qty = self.line.planned_qty
        entry.action_submit()
        self.assertEqual(self.line.qty_done, 0.0)

    def test_reopening_an_entry_rolls_the_plan_line_back(self):
        entry = self._entry_for_line(self.line)
        entry.actual_qty = self.line.planned_qty
        entry.action_submit()
        entry.action_approve()
        self.assertEqual(self.line.state, 'done')

        manager = self._create_user(
            'fmes_mgr_rollback', 'furnishing_mes.group_fmes_manager')
        entry.with_user(manager).action_reset_to_draft()
        self.assertEqual(self.line.qty_done, 0.0)
        self.assertEqual(self.line.state, 'pending')

    def test_shortfall_then_carries_forward(self):
        """The full loop: plan, produce short, approve, replan."""
        entry = self._entry_for_line(self.line)
        entry.actual_qty = self.line.planned_qty / 4.0
        entry.action_submit()
        entry.action_approve()

        follow_on = self.env['fmes.planning.engine'].generate(
            self.day + timedelta(days=1), self.day + timedelta(days=2))
        carried = follow_on.line_ids.filtered(
            lambda l: l.source == 'carry_forward'
            and l.carry_forward_from_id == self.line)
        self.assertTrue(carried, "The shortfall should have been replanned")
        self.assertAlmostEqual(
            sum(carried.mapped('planned_qty')),
            self.line.remaining_qty, places=2)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase4')
class TestEntryGeneration(ExecutionCase):

    def test_entries_are_created_from_a_released_plan(self):
        plan = self._released_plan()
        created = self.env['fmes.production.entry']._generate_from_plan(
            self.day)
        self.assertTrue(created)
        for entry in created:
            self.assertEqual(entry.state, 'draft')
            self.assertTrue(entry.plan_line_id)
            self.assertAlmostEqual(
                entry.planned_qty, entry.plan_line_id.planned_qty, places=4)

    def test_generation_is_idempotent(self):
        self._released_plan()
        Entry = self.env['fmes.production.entry']
        first = Entry._generate_from_plan(self.day)
        second = Entry._generate_from_plan(self.day)
        self.assertTrue(first)
        self.assertFalse(
            second, "Running the generator twice must not duplicate entries")

    def test_draft_plans_produce_no_entries(self):
        self.env['fmes.planning.engine'].generate(self.day, self.day)
        created = self.env['fmes.production.entry']._generate_from_plan(
            self.day)
        self.assertFalse(
            created, "Only released plans should reach the shop floor")


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase4')
class TestOperatorScoping(ExecutionCase):
    """The shared-tablet boundary."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = cls._create_user(
            'fmes_op_scope', 'furnishing_mes.group_fmes_operator')
        cls.other_operator = cls._create_user(
            'fmes_op_other', 'furnishing_mes.group_fmes_operator')
        cls.operator.fmes_workcenter_ids = [(6, 0, [cls.wc_saw.id])]

    def test_assigned_machines_drive_the_allowed_list(self):
        self.assertEqual(
            self.operator.fmes_allowed_workcenter_ids, self.wc_saw)
        self.assertTrue(self.operator.fmes_has_machine_scope)

    def test_department_assignment_expands_to_its_machines(self):
        user = self._create_user(
            'fmes_op_dept', 'furnishing_mes.group_fmes_operator')
        user.fmes_department_ids = [(6, 0, [self.dept_cutting.id])]
        self.assertIn(self.wc_saw, user.fmes_allowed_workcenter_ids)
        self.assertIn(self.wc_edge, user.fmes_allowed_workcenter_ids)
        self.assertNotIn(self.wc_spray, user.fmes_allowed_workcenter_ids)

    def test_operator_sees_entries_on_their_machine(self):
        visible = self.env['fmes.production.entry'].with_user(
            self.operator).search([('id', '=', self.entry.id)])
        self.assertTrue(visible)

    def test_operator_cannot_see_another_machine(self):
        other = self.env['fmes.production.entry'].create({
            'date': self.day,
            'shift_id': self.shift_a.id,
            'workcenter_id': self.wc_spray.id,
            'product_id': self.product_wardrobe.id,
        })
        visible = self.env['fmes.production.entry'].with_user(
            self.operator).search([('id', '=', other.id)])
        self.assertFalse(
            visible, "An operator must not see machines they are not on")

    def test_unassigned_operator_sees_only_their_own_work(self):
        """Not locked out, but not shown the plant either."""
        self.assertFalse(self.other_operator.fmes_has_machine_scope)
        visible = self.env['fmes.production.entry'].with_user(
            self.other_operator).search([('id', '=', self.entry.id)])
        self.assertFalse(visible)

    def test_operator_cannot_edit_an_approved_entry(self):
        self.entry.actual_qty = 50.0
        self.entry.action_submit()
        self.entry.action_approve()
        with self.assertRaises(AccessError):
            self.entry.with_user(self.operator).write({'actual_qty': 60.0})

    def test_operator_cannot_approve(self):
        self.entry.actual_qty = 50.0
        self.entry.action_submit()
        with self.assertRaises(AccessError):
            self.entry.with_user(self.operator).action_approve()

    def test_operator_cannot_delete_entries(self):
        with self.assertRaises(AccessError):
            self.entry.with_user(self.operator).unlink()


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase4')
class TestLiveStatus(ExecutionCase):

    def test_idle_by_default(self):
        self.assertEqual(self.wc_edge.fmes_current_state, 'idle')

    def test_open_breakdown_shows_as_maintenance(self):
        self.env['maintenance.request'].create({
            'name': 'Test breakdown',
            'equipment_id': self.equipment_saw.id,
            'maintenance_type': 'corrective',
        })
        self.wc_saw.invalidate_recordset(['fmes_current_state'])
        self.assertEqual(self.wc_saw.fmes_current_state, 'maintenance')

    def test_today_figures_come_from_entries(self):
        today = self.env['fmes.production.entry'].create({
            'date': fields_today(self.env),
            'shift_id': self.shift_a.id,
            'workcenter_id': self.wc_edge.id,
            'product_id': self.product_wardrobe.id,
            'planned_qty': 50.0,
            'actual_qty': 40.0,
        })
        self.assertTrue(today)
        self.wc_edge.invalidate_recordset(
            ['fmes_today_target', 'fmes_today_produced',
             'fmes_today_achievement'])
        self.assertAlmostEqual(self.wc_edge.fmes_today_target, 50.0, places=4)
        self.assertAlmostEqual(self.wc_edge.fmes_today_produced, 40.0, places=4)
        self.assertAlmostEqual(
            self.wc_edge.fmes_today_achievement, 80.0, places=4)


def fields_today(env):
    from odoo import fields
    return fields.Date.context_today(env['fmes.production.entry'])


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase4')
class TestProductionImport(ExecutionCase):
    """The DAY WISE OUTPUT importer (question Q8)."""

    def _workbook(self, rows, headers=None):
        headers = headers or [
            'Date', 'Shift', 'Machine', 'Product', 'Target', 'Actual Output',
            'Rejected', 'Run Hours', 'Downtime Hrs', 'Manpower', 'Remarks']
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'DAY WISE OUTPUT'
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        stream = io.BytesIO()
        workbook.save(stream)
        return base64.b64encode(stream.getvalue())

    def _wizard(self, rows, **overrides):
        values = {
            'file_data': self._workbook(rows),
            'file_name': 'day_wise_output.xlsx',
            'header_row': 1,
            'default_shift_id': self.shift_a.id,
        }
        values.update(overrides)
        return self.env['fmes.production.import'].create(values)

    def test_headers_are_detected_and_mapped(self):
        wizard = self._wizard([])
        wizard.action_read_headers()
        self.assertEqual(wizard.state, 'map')
        # The mapping is guessed from the column titles, not hard-coded.
        self.assertEqual(wizard.col_date, 'Date')
        self.assertEqual(wizard.col_machine, 'Machine')
        self.assertEqual(wizard.col_actual, 'Actual Output')
        self.assertEqual(wizard.col_rejected, 'Rejected')

    def test_round_trip_import(self):
        rows = [
            ['2026-02-02', 'TA', 'T-SAW-01', 'T-WD-2D', 100, 92, 3, 7, 0.5, 2,
             'ok'],
            ['2026-02-03', 'TA', 'T-SAW-01', 'T-WD-2D', 100, 88, 1, 6.5, 1, 2,
             ''],
        ]
        wizard = self._wizard(rows)
        wizard.action_read_headers()
        wizard.action_preview()
        self.assertEqual(wizard.row_count, 2)
        self.assertEqual(wizard.valid_count, 2)
        self.assertEqual(wizard.error_count, 0)

        action = wizard.action_import()
        batch = self.env['fmes.import.batch'].browse(action['res_id'])
        self.assertEqual(batch.entry_count, 2)

        entry = batch.entry_ids.filtered(
            lambda e: e.date == date(2026, 2, 2))
        self.assertAlmostEqual(entry.actual_qty, 92.0, places=4)
        self.assertAlmostEqual(entry.rejected_qty, 3.0, places=4)
        self.assertAlmostEqual(entry.run_hours, 7.0, places=4)
        self.assertEqual(entry.workcenter_id, self.wc_saw)
        self.assertEqual(entry.product_id, self.product_wardrobe)

    def test_various_date_formats_are_accepted(self):
        """Plants write dates however they like; the importer copes."""
        rows = [
            ['02/02/2026', 'TA', 'T-SAW-01', 'T-WD-2D', 10, 9, 0, 1, 0, 1, ''],
            ['03-02-2026', 'TA', 'T-SAW-01', 'T-WD-2D', 10, 9, 0, 1, 0, 1, ''],
        ]
        wizard = self._wizard(rows)
        wizard.action_read_headers()
        wizard.action_preview()
        self.assertEqual(wizard.valid_count, 2, wizard.preview_html)

    def test_bad_rows_are_reported_not_imported(self):
        rows = [
            ['2026-02-04', 'TA', 'T-SAW-01', 'T-WD-2D', 10, 9, 0, 1, 0, 1, ''],
            ['2026-02-05', 'TA', 'NO-SUCH-MACHINE', 'T-WD-2D', 10, 9, 0, 1, 0,
             1, ''],
            ['not a date', 'TA', 'T-SAW-01', 'T-WD-2D', 10, 9, 0, 1, 0, 1, ''],
            ['2026-02-06', 'TA', 'T-SAW-01', 'T-WD-2D', 10, 5, 8, 1, 0, 1, ''],
        ]
        wizard = self._wizard(rows)
        wizard.action_read_headers()
        wizard.action_preview()
        self.assertEqual(wizard.row_count, 4)
        self.assertEqual(wizard.valid_count, 1)
        self.assertEqual(wizard.error_count, 3)

        action = wizard.action_import()
        batch = self.env['fmes.import.batch'].browse(action['res_id'])
        self.assertEqual(batch.entry_count, 1)
        self.assertIn('unknown machine', batch.log)
        self.assertIn('unreadable date', batch.log)

    def test_duplicate_slots_are_skipped_not_crashed(self):
        rows = [
            [str(self.day), 'TA', 'T-SAW-01', 'T-WD-2D', 100, 90, 0, 7, 0, 2,
             ''],
        ]
        wizard = self._wizard(rows)
        wizard.action_read_headers()
        action = wizard.action_import()
        batch = self.env['fmes.import.batch'].browse(action['res_id'])
        self.assertEqual(batch.entry_count, 0)
        self.assertIn('already exists', batch.log)

    def test_import_can_be_reverted(self):
        rows = [
            ['2026-03-01', 'TA', 'T-SAW-01', 'T-WD-2D', 10, 9, 0, 1, 0, 1, ''],
        ]
        wizard = self._wizard(rows)
        wizard.action_read_headers()
        action = wizard.action_import()
        batch = self.env['fmes.import.batch'].browse(action['res_id'])
        self.assertEqual(batch.entry_count, 1)

        batch.action_revert()
        self.assertEqual(batch.state, 'reverted')
        self.assertEqual(batch.entry_count, 0)

    def test_approved_entries_block_a_revert(self):
        rows = [
            ['2026-03-02', 'TA', 'T-SAW-01', 'T-WD-2D', 10, 9, 0, 1, 0, 1, ''],
        ]
        wizard = self._wizard(rows)
        wizard.action_read_headers()
        action = wizard.action_import()
        batch = self.env['fmes.import.batch'].browse(action['res_id'])
        batch.entry_ids.action_submit()
        batch.entry_ids.action_approve()
        with self.assertRaises(UserError):
            batch.action_revert()

    def test_missing_required_mapping_is_refused(self):
        wizard = self._wizard([])
        wizard.action_read_headers()
        wizard.col_machine = False
        with self.assertRaises(UserError):
            wizard.action_preview()

    def test_unreadable_file_gives_a_useful_message(self):
        wizard = self.env['fmes.production.import'].create({
            'file_data': base64.b64encode(b'this is not a spreadsheet'),
            'file_name': 'notes.txt',
        })
        with self.assertRaises(UserError):
            wizard.action_read_headers()


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase4')
class TestShopFloorTerminal(HttpCase):
    """The terminal endpoints, exercised as a real operator over HTTP."""

    def setUp(self):
        super().setUp()
        self.shift = self.env['fmes.shift'].create({
            'name': 'Terminal Shift', 'code': 'TT',
            'start_time': 6.0, 'end_time': 14.0, 'break_minutes': 30,
        })
        self.department = self.env['hr.department'].create(
            {'name': 'Terminal Dept'})
        self.machine = self.env['mrp.workcenter'].create({
            'name': 'Terminal Machine', 'code': 'T-TERM',
            'fmes_machine_code': 'T-TERM-01',
            'department_id': self.department.id,
        })
        self.other_machine = self.env['mrp.workcenter'].create({
            'name': 'Off Limits Machine', 'code': 'T-OFF'})
        self.category = self.env['product.category'].create(
            {'name': 'Terminal Category'})
        self.product = self.env['product.product'].create({
            'name': 'Terminal Product', 'categ_id': self.category.id})
        self.env['fmes.capacity.matrix'].create({
            'workcenter_id': self.machine.id,
            'product_id': self.product.id,
            'std_output_qty': 10.0,
        })
        self.entry = self.env['fmes.production.entry'].create({
            'date': fields_today(self.env),
            'shift_id': self.shift.id,
            'workcenter_id': self.machine.id,
            'product_id': self.product.id,
            'planned_qty': 60.0,
        })
        self.blocked_entry = self.env['fmes.production.entry'].create({
            'date': fields_today(self.env),
            'shift_id': self.shift.id,
            'workcenter_id': self.other_machine.id,
            'product_id': self.product.id,
            'planned_qty': 10.0,
        })

        self.operator = self.env['res.users'].create({
            'name': 'Terminal Operator',
            'login': 'fmes_terminal_op',
            'password': 'fmes_terminal_op',
            'groups_id': [(6, 0, [
                self.env.ref('furnishing_mes.group_fmes_operator').id])],
            'fmes_workcenter_ids': [(6, 0, [self.machine.id])],
        })

    def test_machine_list_is_scoped_to_the_operator(self):
        self.authenticate('fmes_terminal_op', 'fmes_terminal_op')
        data = self.make_jsonrpc_request('/fmes/terminal/machines', {})
        ids = [m['id'] for m in data['machines']]
        self.assertIn(self.machine.id, ids)
        self.assertNotIn(
            self.other_machine.id, ids,
            "The picker must not offer a machine the operator is not on")
        self.assertTrue(data['scoped'])

    def test_board_returns_the_shift_entries(self):
        self.authenticate('fmes_terminal_op', 'fmes_terminal_op')
        data = self.make_jsonrpc_request('/fmes/terminal/board', {
            'workcenter_id': self.machine.id,
            'shift_id': self.shift.id,
        })
        self.assertEqual(data['machine']['id'], self.machine.id)
        self.assertEqual(len(data['entries']), 1)
        self.assertTrue(data['entries'][0]['editable'])

    def test_recording_output_saves(self):
        self.authenticate('fmes_terminal_op', 'fmes_terminal_op')
        result = self.make_jsonrpc_request('/fmes/terminal/record', {
            'entry_id': self.entry.id,
            'values': {'actual_qty': 42.0, 'rejected_qty': 2.0},
        })
        self.assertTrue(result['ok'], result.get('error'))
        self.entry.invalidate_recordset()
        self.assertAlmostEqual(self.entry.actual_qty, 42.0, places=4)
        self.assertAlmostEqual(self.entry.rejected_qty, 2.0, places=4)

    def test_only_permitted_fields_are_written(self):
        """A tablet must not be able to set a field it has no business setting."""
        self.authenticate('fmes_terminal_op', 'fmes_terminal_op')
        result = self.make_jsonrpc_request('/fmes/terminal/record', {
            'entry_id': self.entry.id,
            'values': {'actual_qty': 10.0, 'state': 'approved',
                       'planned_qty': 99999.0},
        })
        self.assertTrue(result['ok'])
        self.entry.invalidate_recordset()
        self.assertEqual(self.entry.state, 'draft')
        self.assertAlmostEqual(self.entry.planned_qty, 60.0, places=4)

    def test_recording_on_another_machine_is_refused(self):
        """A graceful {ok: False}, not a raised exception over the wire.

        make_jsonrpc_request raises JsonRpcException itself whenever an
        exception escapes the controller uncaught, so this is a stricter
        check than searching the raw response text for the word "error" —
        that string is present either way, which is what let a real gap
        (the whole route body needs to be inside the try/except, not just
        the write() call — Phase 5, D5.3) go unnoticed here originally.
        """
        self.authenticate('fmes_terminal_op', 'fmes_terminal_op')
        result = self.make_jsonrpc_request('/fmes/terminal/record', {
            'entry_id': self.blocked_entry.id,
            'values': {'actual_qty': 5.0},
        })
        self.assertFalse(result['ok'])
        self.blocked_entry.invalidate_recordset()
        self.assertEqual(self.blocked_entry.actual_qty, 0.0)

    def _json_payload(self, params):
        import json
        return json.dumps({
            'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': params})

    def test_submitting_locks_the_shift(self):
        self.authenticate('fmes_terminal_op', 'fmes_terminal_op')
        self.make_jsonrpc_request('/fmes/terminal/record', {
            'entry_id': self.entry.id,
            'values': {'actual_qty': 55.0},
        })
        result = self.make_jsonrpc_request('/fmes/terminal/submit', {
            'entry_ids': [self.entry.id],
        })
        self.assertTrue(result['ok'], result.get('error'))
        self.entry.invalidate_recordset()
        self.assertEqual(self.entry.state, 'submitted')

        again = self.make_jsonrpc_request('/fmes/terminal/record', {
            'entry_id': self.entry.id,
            'values': {'actual_qty': 999.0},
        })
        self.assertFalse(again['ok'])
        self.entry.invalidate_recordset()
        self.assertAlmostEqual(self.entry.actual_qty, 55.0, places=4)

    def test_terminal_requires_a_login(self):
        response = self.url_open(
            '/fmes/terminal/machines',
            data=self._json_payload({}),
            headers={'Content-Type': 'application/json'},
            timeout=60)
        self.assertIn('error', response.text)
