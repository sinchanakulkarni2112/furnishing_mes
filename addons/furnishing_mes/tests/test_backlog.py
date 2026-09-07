# -*- coding: utf-8 -*-
"""Phase 9 tests: backlog snapshots, order blocking and carry-forward
automation.

Three things matter most here. The nightly snapshot must be idempotent — a
re-run for the same date must converge to the same single row per order, not
duplicate or silently skip. Classification boundaries (pending / at-risk /
delayed / blocked / completed) must match assumptions A26/A32/A53 exactly,
since a wrongly-classified row is worse than a missing one. And a blocked
order must actually disappear from what the planning engine offers a slot to
— "excluded from auto-scheduling" is a testable claim, not a UI label.
"""

from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import FmesTestCase

REFERENCE_DATE = date(2026, 1, 20)


class BacklogCase(FmesTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env['fmes.backlog.service']

    @classmethod
    def _mo(cls, product=None, qty=100.0, deadline=None, **vals):
        base = {
            'product_id': (product or cls.product_wardrobe).id,
            'product_qty': qty,
            'date_deadline': deadline,
        }
        base.update(vals)
        return cls.env['mrp.production'].create(base)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase9')
class TestBacklogClassification(BacklogCase):
    """`_classify` in isolation — pure maths, no stock-move plumbing."""

    def test_pending_when_comfortably_before_deadline(self):
        pending, pct, delayed, status = self.service._classify(
            100.0, 0.0, REFERENCE_DATE + timedelta(days=10),
            REFERENCE_DATE, False)
        self.assertEqual(pending, 100.0)
        self.assertEqual(pct, 0.0)
        self.assertEqual(delayed, 0)
        self.assertEqual(status, 'pending')

    def test_at_risk_within_the_lookahead_window(self):
        # Assumption A53: due within 3 days, still incomplete.
        _p, _c, delayed, status = self.service._classify(
            100.0, 50.0, REFERENCE_DATE + timedelta(days=3),
            REFERENCE_DATE, False)
        self.assertEqual(delayed, 0)
        self.assertEqual(status, 'at_risk')

    def test_not_yet_at_risk_beyond_the_lookahead_window(self):
        _p, _c, _d, status = self.service._classify(
            100.0, 50.0, REFERENCE_DATE + timedelta(days=4),
            REFERENCE_DATE, False)
        self.assertEqual(status, 'pending')

    def test_delayed_the_day_after_the_deadline(self):
        pending, _pct, delayed, status = self.service._classify(
            100.0, 60.0, REFERENCE_DATE - timedelta(days=1),
            REFERENCE_DATE, False)
        self.assertEqual(delayed, 1)
        self.assertEqual(status, 'delayed')
        self.assertEqual(pending, 40.0)

    def test_no_deadline_is_never_delayed_or_at_risk(self):
        _p, _c, delayed, status = self.service._classify(
            100.0, 0.0, False, REFERENCE_DATE, False)
        self.assertEqual(delayed, 0)
        self.assertEqual(status, 'pending')

    def test_blocked_overrides_delayed(self):
        """A blocked, overdue order is still reported as blocked — that is
        the actionable fact, not the lateness it causes."""
        _p, _c, _d, status = self.service._classify(
            100.0, 0.0, REFERENCE_DATE - timedelta(days=5),
            REFERENCE_DATE, True)
        self.assertEqual(status, 'blocked')

    def test_completed_overrides_blocked(self):
        _p, _c, _d, status = self.service._classify(
            100.0, 100.0, REFERENCE_DATE - timedelta(days=5),
            REFERENCE_DATE, True)
        self.assertEqual(status, 'completed')

    def test_completion_pct_and_pending_qty_maths(self):
        pending, pct, _d, _s = self.service._classify(
            80.0, 30.0, False, REFERENCE_DATE, False)
        self.assertEqual(pending, 50.0)
        self.assertAlmostEqual(pct, 37.5, places=4)

    def test_zero_ordered_qty_guards_the_division(self):
        pending, pct, _d, status = self.service._classify(
            0.0, 0.0, False, REFERENCE_DATE, False)
        self.assertEqual(pending, 0.0)
        self.assertEqual(pct, 0.0)
        self.assertEqual(status, 'completed',
                         "Nothing ordered, nothing pending - trivially done")

    def test_overproduction_never_yields_negative_pending(self):
        pending, _pct, _d, _s = self.service._classify(
            50.0, 70.0, False, REFERENCE_DATE, False)
        self.assertEqual(pending, 0.0)

    def test_days_delayed_floors_at_zero_not_negative(self):
        _p, _c, delayed, _s = self.service._classify(
            100.0, 0.0, REFERENCE_DATE + timedelta(days=30),
            REFERENCE_DATE, False)
        self.assertEqual(delayed, 0)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase9')
class TestBacklogSnapshotWrite(BacklogCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.supervisor = cls._create_user(
            'fmes_bl_sup', 'furnishing_mes.group_fmes_supervisor')

    def test_snapshot_creates_one_row_per_open_order(self):
        mo = self._mo(deadline=REFERENCE_DATE + timedelta(days=5))
        self.service._write_snapshot_for_company(
            REFERENCE_DATE, self.company)
        row = self.env['fmes.backlog.snapshot'].sudo().search([
            ('production_id', '=', mo.id),
            ('snapshot_date', '=', REFERENCE_DATE),
        ])
        self.assertEqual(len(row), 1)
        self.assertEqual(row.pending_qty, 100.0)
        self.assertEqual(row.status, 'pending')

    def test_done_and_cancelled_orders_are_excluded(self):
        mo = self._mo()
        mo.state = 'cancel'
        self.service._write_snapshot_for_company(
            REFERENCE_DATE, self.company)
        row = self.env['fmes.backlog.snapshot'].sudo().search([
            ('production_id', '=', mo.id)])
        self.assertFalse(row)

    def test_rerunning_for_the_same_date_is_idempotent(self):
        mo = self._mo(deadline=REFERENCE_DATE + timedelta(days=5))
        self.service._write_snapshot_for_company(
            REFERENCE_DATE, self.company)
        self.service._write_snapshot_for_company(
            REFERENCE_DATE, self.company)
        rows = self.env['fmes.backlog.snapshot'].sudo().search([
            ('production_id', '=', mo.id),
            ('snapshot_date', '=', REFERENCE_DATE),
        ])
        self.assertEqual(len(rows), 1,
                         "A second run for the same date must converge, "
                         "not duplicate")

    def test_rerunning_reflects_data_that_changed_since_the_first_run(self):
        mo = self._mo(deadline=REFERENCE_DATE + timedelta(days=5))
        self.service._write_snapshot_for_company(
            REFERENCE_DATE, self.company)
        mo.with_user(self.supervisor).action_fmes_mark_blocked('material')
        self.service._write_snapshot_for_company(
            REFERENCE_DATE, self.company)
        row = self.env['fmes.backlog.snapshot'].sudo().search([
            ('production_id', '=', mo.id),
            ('snapshot_date', '=', REFERENCE_DATE),
        ])
        self.assertEqual(row.status, 'blocked')

    def test_different_dates_accumulate_history(self):
        mo = self._mo(deadline=REFERENCE_DATE + timedelta(days=5))
        self.service._write_snapshot_for_company(
            REFERENCE_DATE, self.company)
        self.service._write_snapshot_for_company(
            REFERENCE_DATE + timedelta(days=1), self.company)
        rows = self.env['fmes.backlog.snapshot'].sudo().search([
            ('production_id', '=', mo.id)])
        self.assertEqual(len(rows), 2)

    def test_backlog_age_drives_criticality_independent_of_deadline(self):
        mo = self._mo(deadline=REFERENCE_DATE + timedelta(days=60))
        day = REFERENCE_DATE
        for offset in range(17):
            self.service._write_snapshot_for_company(
                day + timedelta(days=offset), self.company)
        rows = self.env['fmes.backlog.snapshot'].sudo().search([
            ('production_id', '=', mo.id)], order='snapshot_date asc')
        self.assertFalse(rows[14].is_critical, "Day 15 in the backlog: not yet")
        self.assertTrue(
            rows[16].is_critical,
            "Day 17 in the backlog, still nowhere near its own deadline - "
            "criticality here is about age, not lateness")


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase9')
class TestOrderBlocking(BacklogCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supervisor = cls._create_user(
            'fmes_block_sup', 'furnishing_mes.group_fmes_supervisor')
        cls.operator = cls._create_user(
            'fmes_block_op', 'furnishing_mes.group_fmes_operator')

    def test_marking_blocked_sets_the_flag_and_audit_fields(self):
        mo = self._mo()
        mo.with_user(self.supervisor).action_fmes_mark_blocked(
            'manpower', note='Short a setter this week')
        self.assertTrue(mo.fmes_is_blocked)
        self.assertEqual(mo.fmes_block_reason, 'manpower')
        self.assertEqual(mo.fmes_blocked_by, self.supervisor)
        self.assertTrue(mo.fmes_blocked_on)

    def test_clearing_the_block_resets_everything(self):
        mo = self._mo()
        mo.with_user(self.supervisor).action_fmes_mark_blocked('quality')
        mo.with_user(self.supervisor).action_fmes_clear_block()
        self.assertFalse(mo.fmes_is_blocked)
        self.assertFalse(mo.fmes_block_reason)
        self.assertFalse(mo.fmes_blocked_by)

    def test_operator_cannot_block_an_order(self):
        mo = self._mo()
        with self.assertRaises(AccessError):
            mo.with_user(self.operator).action_fmes_mark_blocked('material')

    def test_blocked_order_is_excluded_from_auto_scheduling(self):
        mo = self._mo(deadline=REFERENCE_DATE + timedelta(days=2))
        mo.with_user(self.supervisor).action_fmes_mark_blocked('machine')
        demands = self.env['fmes.planning.engine']._demands_for_production(
            mo)
        self.assertEqual(demands, [])

    def test_an_unblocked_order_still_produces_demand(self):
        mo = self._mo(deadline=REFERENCE_DATE + timedelta(days=2))
        demands = self.env['fmes.planning.engine']._demands_for_production(
            mo)
        self.assertTrue(demands)

    def test_plan_line_mirrors_the_source_orders_block_state(self):
        plan = self.env['fmes.production.plan'].create({
            'plan_type': 'daily', 'date_from': REFERENCE_DATE,
            'date_to': REFERENCE_DATE,
        })
        mo = self._mo()
        line = self.env['fmes.production.plan.line'].create({
            'plan_id': plan.id, 'date': REFERENCE_DATE,
            'shift_id': self.shift_a.id, 'workcenter_id': self.wc_saw.id,
            'product_id': self.product_wardrobe.id, 'production_id': mo.id,
            'planned_qty': 10.0,
        })
        self.assertFalse(line.fmes_is_blocked)
        mo.with_user(self.supervisor).action_fmes_mark_blocked('other')
        line.invalidate_recordset(['fmes_is_blocked'])
        self.assertTrue(line.fmes_is_blocked)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase9')
class TestCarryForwardCron(BacklogCase):

    def test_generates_tomorrows_plan(self):
        Engine = self.env['fmes.planning.engine']
        plan = Engine._cron_generate_carry_forward_plan()
        self.assertTrue(plan)
        self.assertEqual(plan.generated_by, 'auto')

    def test_idempotent_when_an_auto_plan_already_exists(self):
        Engine = self.env['fmes.planning.engine']
        first = Engine._cron_generate_carry_forward_plan()
        second = Engine._cron_generate_carry_forward_plan()
        self.assertEqual(first, second)
        self.assertEqual(
            self.env['fmes.production.plan'].search_count([
                ('date_from', '=', first.date_from),
                ('date_to', '=', first.date_from),
                ('generated_by', '=', 'auto'),
            ]), 1)

    def test_a_plan_already_covering_tomorrow_is_not_duplicated(self):
        """Whatever created tomorrow's auto plan first — a supervisor
        running Generate Plan by hand, or an earlier cron tick — the cron
        must find and return it rather than create a second one."""
        Engine = self.env['fmes.planning.engine']
        tomorrow = fields.Date.context_today(self.env.user) + timedelta(
            days=1)
        earlier = Engine.generate(tomorrow, tomorrow, plan_type='daily')
        cron_result = Engine._cron_generate_carry_forward_plan()
        self.assertEqual(earlier, cron_result)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase9')
class TestBacklogSecurity(BacklogCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = cls._create_user(
            'fmes_bl_sec_op', 'furnishing_mes.group_fmes_operator')

    def test_operator_cannot_read_the_backlog(self):
        with self.assertRaises(AccessError):
            self.env['fmes.backlog.snapshot'].with_user(
                self.operator).search([])

    def test_ui_cannot_create_or_edit_a_snapshot_row(self):
        supervisor = self._create_user(
            'fmes_bl_sec_sup', 'furnishing_mes.group_fmes_supervisor')
        with self.assertRaises(AccessError):
            self.env['fmes.backlog.snapshot'].with_user(supervisor).create({
                'snapshot_date': REFERENCE_DATE,
                'product_id': self.product_wardrobe.id,
                'status': 'pending',
            })

    def test_supervisor_with_assigned_department_is_scoped_to_it(self):
        supervisor = self._create_user(
            'fmes_bl_sec_sup2', 'furnishing_mes.group_fmes_supervisor')
        supervisor.fmes_department_ids = [(6, 0, [self.dept_cutting.id])]
        Snapshot = self.env['fmes.backlog.snapshot'].sudo()
        cutting_row = Snapshot.create({
            'snapshot_date': REFERENCE_DATE,
            'product_id': self.product_wardrobe.id,
            'department_id': self.dept_cutting.id, 'status': 'pending',
        })
        finishing_row = Snapshot.create({
            'snapshot_date': REFERENCE_DATE,
            'product_id': self.product_wardrobe.id,
            'department_id': self.dept_finishing.id, 'status': 'pending',
        })
        visible = self.env['fmes.backlog.snapshot'].with_user(
            supervisor).search([])
        self.assertIn(cutting_row, visible)
        self.assertNotIn(finishing_row, visible)

    def test_manager_sees_every_department(self):
        manager = self._create_user(
            'fmes_bl_sec_mgr', 'furnishing_mes.group_fmes_manager')
        row = self.env['fmes.backlog.snapshot'].sudo().create({
            'snapshot_date': REFERENCE_DATE,
            'product_id': self.product_wardrobe.id,
            'department_id': self.dept_finishing.id, 'status': 'pending',
        })
        visible = self.env['fmes.backlog.snapshot'].with_user(
            manager).search([('id', '=', row.id)])
        self.assertTrue(visible)
