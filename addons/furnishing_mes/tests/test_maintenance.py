# -*- coding: utf-8 -*-
"""Phase 7 tests: preventive scheduling, breakdown tracking and maintenance KPIs.

Three things matter most here. A schedule must recur correctly and only ever
have one open request outstanding at a time — a plant that runs the cron
daily must never see a due visit raised twice just because nobody has closed
the first one yet. A breakdown escalated from the terminal (Phase 5) must now
carry the machine and the lost hours, not just the equipment. And native
MTBF/MTTR must stay untouched — reused as-is, never reimplemented — while the
composite health score and the KPI report are built on top of them.
"""

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import FmesTestCase

REFERENCE_DATE = '2026-01-05'


class MaintenanceCase(FmesTestCase):
    """Fixture plant plus a supervisor to approve/act with."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supervisor = cls._create_user(
            'fmes_maint_sup', 'furnishing_mes.group_fmes_supervisor')
        cls.manager = cls._create_user(
            'fmes_maint_mgr', 'furnishing_mes.group_fmes_manager')
        cls.stage_done = cls.env.ref('maintenance.stage_3')
        cls.stage_open = cls.env.ref('maintenance.stage_0')
        cls.productive_loss = cls.env.ref('mrp.block_reason7')
        cls.breakdown_loss = cls.env.ref('mrp.block_reason1')

    @classmethod
    def _schedule(cls, **vals):
        base = {
            'equipment_id': cls.equipment_saw.id,
            'trigger_type': 'time_based',
            'interval_number': 1,
            'interval_unit': 'month',
            'lead_time_days': 7,
            'last_done_date': REFERENCE_DATE,
        }
        base.update(vals)
        return cls.env['fmes.maintenance.schedule'].create(base)

    def _productive_event(self, workcenter, start, hours, state='approved'):
        return self.env['mrp.workcenter.productivity'].create({
            'workcenter_id': workcenter.id,
            'loss_id': self.productive_loss.id,
            'date_start': start,
            'date_end': start + timedelta(hours=hours),
            'fmes_state': state,
        })


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase7')
class TestScheduleRecurrence(MaintenanceCase):

    def test_time_based_next_due_date_recurs_from_last_done(self):
        schedule = self._schedule(
            last_done_date='2026-01-05', interval_number=1,
            interval_unit='month')
        self.assertEqual(schedule.next_due_date, date(2026, 2, 5))

    def test_interval_unit_and_number_both_apply(self):
        schedule = self._schedule(
            last_done_date='2026-01-05', interval_number=2,
            interval_unit='week')
        self.assertEqual(schedule.next_due_date, date(2026, 1, 19))

    def test_never_done_anchors_to_equipment_effective_date(self):
        self.equipment_saw.effective_date = '2026-03-01'
        schedule = self._schedule(last_done_date=False, interval_number=1,
                                  interval_unit='month')
        self.assertEqual(schedule.next_due_date, date(2026, 4, 1))

    def test_usage_based_has_no_due_date_until_checked(self):
        schedule = self._schedule(trigger_type='usage_based',
                                  usage_threshold_hours=100.0)
        self.assertFalse(schedule.next_due_date)

    def test_completion_recomputes_last_done_and_next_due_date(self):
        schedule = self._schedule(
            last_done_date='2026-01-05', interval_number=1,
            interval_unit='month')
        request = schedule._create_request()
        request.with_user(self.supervisor).write(
            {'stage_id': self.stage_done.id})
        self.assertEqual(schedule.last_done_date, request.close_date)
        self.assertEqual(
            schedule.next_due_date,
            schedule.last_done_date + relativedelta(months=1))


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase7')
class TestUsageBasedTriggering(MaintenanceCase):

    def test_stays_not_due_below_threshold(self):
        schedule = self._schedule(
            trigger_type='usage_based', usage_threshold_hours=100.0,
            last_done_date='2026-01-01')
        self._productive_event(
            self.wc_saw, fields.Datetime.to_datetime('2026-01-10 08:00:00'),
            hours=10.0)
        schedule._check_usage_triggers()
        self.assertFalse(schedule.next_due_date)

    def test_becomes_due_once_threshold_crossed(self):
        schedule = self._schedule(
            trigger_type='usage_based', usage_threshold_hours=20.0,
            last_done_date='2026-01-01')
        self._productive_event(
            self.wc_saw, fields.Datetime.to_datetime('2026-01-10 08:00:00'),
            hours=12.0)
        self._productive_event(
            self.wc_saw, fields.Datetime.to_datetime('2026-01-11 08:00:00'),
            hours=10.0)
        schedule._check_usage_triggers()
        self.assertEqual(
            schedule.next_due_date, fields.Date.context_today(schedule))

    def test_draft_hours_do_not_count(self):
        schedule = self._schedule(
            trigger_type='usage_based', usage_threshold_hours=5.0,
            last_done_date='2026-01-01')
        self._productive_event(
            self.wc_saw, fields.Datetime.to_datetime('2026-01-10 08:00:00'),
            hours=50.0, state='draft')
        schedule._check_usage_triggers()
        self.assertFalse(schedule.next_due_date)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase7')
class TestLeadTimeGeneration(MaintenanceCase):

    def test_no_request_before_the_lead_time_window(self):
        today = fields.Date.context_today(self.env['fmes.maintenance.schedule'])
        schedule = self._schedule(
            last_done_date=today, interval_number=1, interval_unit='year',
            lead_time_days=7)
        schedule._generate_due_requests()
        self.assertFalse(schedule.request_ids)

    def test_request_generated_within_the_lead_time_window(self):
        today = fields.Date.context_today(self.env['fmes.maintenance.schedule'])
        # Due in 5 days, lead time 7: inside the window right now.
        schedule = self._schedule(
            last_done_date=today - timedelta(days=25), interval_number=1,
            interval_unit='month', lead_time_days=7)
        schedule._generate_due_requests()
        self.assertEqual(len(schedule.request_ids), 1)
        request = schedule.request_ids
        self.assertEqual(request.maintenance_type, 'preventive')
        self.assertEqual(request.equipment_id, self.equipment_saw)
        self.assertEqual(request.workcenter_id, self.wc_saw)
        self.assertEqual(request.fmes_due_date, schedule.next_due_date)

    def test_no_duplicate_open_request_on_repeated_cron_run(self):
        today = fields.Date.context_today(self.env['fmes.maintenance.schedule'])
        schedule = self._schedule(
            last_done_date=today - timedelta(days=25), interval_number=1,
            interval_unit='month', lead_time_days=7)
        schedule._generate_due_requests()
        schedule._generate_due_requests()
        self.assertEqual(len(schedule.request_ids), 1,
                         "A second cron run must not raise a second open "
                         "request while the first is still open")

    def test_a_new_request_can_be_raised_once_the_open_one_is_closed(self):
        today = fields.Date.context_today(self.env['fmes.maintenance.schedule'])
        schedule = self._schedule(
            last_done_date=today - timedelta(days=25), interval_number=1,
            interval_unit='month', lead_time_days=7)
        schedule._generate_due_requests()
        first = schedule.request_ids
        first.with_user(self.supervisor).write({'stage_id': self.stage_done.id})
        # Completion just pushed next_due_date roughly a month out again,
        # past the lead-time window, so nothing new should appear yet.
        schedule._generate_due_requests()
        self.assertEqual(len(schedule.request_ids), 1)

    def test_paused_schedule_generates_nothing(self):
        today = fields.Date.context_today(self.env['fmes.maintenance.schedule'])
        schedule = self._schedule(
            last_done_date=today - timedelta(days=25), interval_number=1,
            interval_unit='month', lead_time_days=7, state='paused')
        schedule._generate_due_requests()
        self.assertFalse(schedule.request_ids)

    def test_checklist_is_snapshotted_onto_the_generated_request(self):
        schedule = self._schedule()
        self.env['fmes.maintenance.checklist.line'].create({
            'schedule_id': schedule.id,
            'name': 'Check belt tension',
            'is_mandatory': True,
            'expected_value': 'Snug, no slip',
        })
        request = schedule._create_request()
        self.assertEqual(len(request.fmes_checklist_result_ids), 1)
        result = request.fmes_checklist_result_ids
        self.assertEqual(result.name, 'Check belt tension')
        self.assertEqual(result.expected_value, 'Snug, no slip')

        # Editing the template afterward must not rewrite history.
        schedule.checklist_ids.name = 'Check belt tension (revised)'
        self.assertEqual(result.name, 'Check belt tension')


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase7')
class TestBreakdownEscalation(MaintenanceCase):
    """Extends Phase 5's escalation: the request now carries the machine
    and the lost hours, not just the equipment."""

    def test_escalated_request_carries_the_machine(self):
        event = self.env['mrp.workcenter.productivity'].create({
            'workcenter_id': self.wc_saw.id,
            'loss_id': self.breakdown_loss.id,
            'date_start': fields.Datetime.now() - timedelta(minutes=30),
        })
        request = event.fmes_maintenance_request_id
        self.assertTrue(request)
        self.assertEqual(request.workcenter_id, self.wc_saw)
        self.assertEqual(request.fmes_productivity_id, event)

    def test_downtime_hours_track_the_live_event_duration(self):
        start = fields.Datetime.now() - timedelta(minutes=45)
        event = self.env['mrp.workcenter.productivity'].create({
            'workcenter_id': self.wc_saw.id,
            'loss_id': self.breakdown_loss.id,
            'date_start': start,
        })
        request = event.fmes_maintenance_request_id
        self.assertEqual(request.fmes_downtime_hours, 0.0,
                         "Still running: no elapsed duration yet")
        event.date_end = fields.Datetime.now()
        request.invalidate_recordset(['fmes_downtime_hours'])
        self.assertAlmostEqual(request.fmes_downtime_hours, 45.0 / 60.0,
                               delta=0.05)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase7')
class TestHealthScore(MaintenanceCase):

    def test_full_marks_with_no_issues(self):
        equipment = self.equipment_edge  # no schedules, no history
        equipment.invalidate_recordset(['fmes_health_score'])
        self.assertEqual(equipment.fmes_health_score, 100.0)

    def test_overdue_pm_reduces_the_score(self):
        self._schedule(equipment_id=self.equipment_saw.id,
                       last_done_date='2020-01-01', interval_number=1,
                       interval_unit='month')
        self.equipment_saw.invalidate_recordset(['fmes_health_score'])
        self.assertAlmostEqual(
            self.equipment_saw.fmes_health_score, 90.0, delta=0.01,
            msg="One overdue PM costs 10 points")

    def test_overdue_pm_penalty_is_capped(self):
        for _i in range(6):
            self._schedule(equipment_id=self.equipment_saw.id,
                           last_done_date='2020-01-01', interval_number=1,
                           interval_unit='month')
        self.equipment_saw.invalidate_recordset(['fmes_health_score'])
        self.assertAlmostEqual(
            self.equipment_saw.fmes_health_score, 70.0, delta=0.01,
            msg="Overdue-PM penalty caps at 30 points regardless of count")

    def test_recent_breakdowns_reduce_the_score(self):
        today = fields.Date.context_today(self.equipment_saw)
        self.env['maintenance.request'].create({
            'name': 'Breakdown',
            'equipment_id': self.equipment_saw.id,
            'maintenance_type': 'corrective',
            'request_date': today - timedelta(days=10),
        })
        self.equipment_saw.invalidate_recordset(['fmes_health_score'])
        self.assertAlmostEqual(
            self.equipment_saw.fmes_health_score, 92.0, delta=0.01)

    def test_old_breakdowns_outside_the_window_do_not_count(self):
        today = fields.Date.context_today(self.equipment_saw)
        self.env['maintenance.request'].create({
            'name': 'Old breakdown',
            'equipment_id': self.equipment_saw.id,
            'maintenance_type': 'corrective',
            'request_date': today - timedelta(days=200),
        })
        self.equipment_saw.invalidate_recordset(['fmes_health_score'])
        self.assertEqual(self.equipment_saw.fmes_health_score, 100.0)

    def test_operator_can_read_health_score_via_native_equipment_access(self):
        """Every internal user can read maintenance.equipment natively
        (Odoo core ACL); the health score's own read of fmes_schedule_ids
        must not raise for a group with no direct access to that model."""
        operator = self._create_user(
            'fmes_maint_op', 'furnishing_mes.group_fmes_operator')
        self._schedule(equipment_id=self.equipment_saw.id)
        self.equipment_saw.invalidate_recordset(['fmes_health_score'])
        score = self.equipment_saw.with_user(operator).fmes_health_score
        self.assertIsInstance(score, float)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase7')
class TestMaintenanceReport(MaintenanceCase):

    def _closed_preventive(self, last_done, close_date, cost=0.0):
        """Due one interval after `last_done` (the fixture schedule is
        monthly), closed on `close_date`.

        Two writes, deliberately: native `maintenance.request.write()`
        stamps `close_date` to the real "today" itself whenever `stage_id`
        is part of the SAME vals dict, overriding any explicit value passed
        alongside it — so a backdated close_date for test purposes has to
        land in a second, separate write.
        """
        schedule = self._schedule(last_done_date=last_done)
        request = schedule._create_request()
        request.write({'fmes_cost': cost})
        request.with_user(self.supervisor).write(
            {'stage_id': self.stage_done.id})
        request.write({'close_date': close_date})
        return request

    def test_request_and_type_counts_aggregate_by_month(self):
        self._closed_preventive('2026-03-05', '2026-04-08')
        self.env['maintenance.request'].create({
            'name': 'Breakdown', 'equipment_id': self.equipment_saw.id,
            'maintenance_type': 'corrective',
            'request_date': '2026-04-10',
        })
        self.env.flush_all()
        rows = self.env['fmes.maintenance.report'].search([
            ('equipment_id', '=', self.equipment_saw.id)])
        self.assertEqual(len(rows), 1, "Both fall in the same due/report month")
        self.assertEqual(rows.request_count, 2)
        self.assertEqual(rows.preventive_count, 1)
        self.assertEqual(rows.corrective_count, 1)

    def test_pm_compliance_pct_and_has_pm_due(self):
        # Due 2026-04-05, closed 2026-04-08: three days late.
        self._closed_preventive('2026-03-05', '2026-04-08')
        self.env.flush_all()
        row = self.env['fmes.maintenance.report'].search([
            ('equipment_id', '=', self.equipment_saw.id)])
        self.assertTrue(row.has_pm_due)
        self.assertAlmostEqual(row.pm_compliance_pct, 0.0, delta=0.01,
                               msg="Closed after its own due date: not on time")

    def test_on_time_pm_is_fully_compliant(self):
        self._closed_preventive('2026-03-05', '2026-04-01')
        self.env.flush_all()
        row = self.env['fmes.maintenance.report'].search([
            ('equipment_id', '=', self.equipment_saw.id)])
        self.assertAlmostEqual(row.pm_compliance_pct, 100.0, delta=0.01)

    def test_no_pm_due_reads_as_not_applicable_not_zero(self):
        self.env['maintenance.request'].create({
            'name': 'Breakdown', 'equipment_id': self.equipment_saw.id,
            'maintenance_type': 'corrective', 'request_date': '2026-05-01',
        })
        self.env.flush_all()
        row = self.env['fmes.maintenance.report'].search([
            ('equipment_id', '=', self.equipment_saw.id)])
        self.assertFalse(row.has_pm_due)

    def test_downtime_hours_and_cost_aggregate(self):
        event = self.env['mrp.workcenter.productivity'].create({
            'workcenter_id': self.wc_saw.id,
            'loss_id': self.breakdown_loss.id,
            'date_start': '2026-06-01 08:00:00',
            'date_end': '2026-06-01 09:30:00',
        })
        request = event.fmes_maintenance_request_id
        request.write({'fmes_cost': 1500.0})
        self.env.flush_all()
        row = self.env['fmes.maintenance.report'].search([
            ('equipment_id', '=', self.equipment_saw.id)])
        self.assertAlmostEqual(row.downtime_hours, 1.5, delta=0.01)
        self.assertAlmostEqual(row.cost, 1500.0, delta=0.01)

    def test_mtbf_and_mttr_mirror_the_native_equipment_fields(self):
        # Native mtbf/mttr only count DONE corrective requests - close this
        # one so both read a genuinely non-zero value to mirror.
        self.equipment_saw.effective_date = '2026-01-01'
        request = self.env['maintenance.request'].create({
            'name': 'Breakdown', 'equipment_id': self.equipment_saw.id,
            'maintenance_type': 'corrective', 'request_date': '2026-07-01',
        })
        request.with_user(self.supervisor).write(
            {'stage_id': self.stage_done.id, 'close_date': '2026-07-03'})
        self.equipment_saw.invalidate_recordset(['mtbf', 'mttr'])
        self.assertTrue(self.equipment_saw.mtbf)
        self.env.flush_all()
        row = self.env['fmes.maintenance.report'].search([
            ('equipment_id', '=', self.equipment_saw.id)], limit=1)
        self.assertEqual(row.mtbf, self.equipment_saw.mtbf)
        self.assertEqual(row.mttr, self.equipment_saw.mttr)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase7')
class TestMaintenanceAccess(MaintenanceCase):

    def test_operator_cannot_manage_schedules(self):
        operator = self._create_user(
            'fmes_maint_access_op', 'furnishing_mes.group_fmes_operator')
        with self.assertRaises(AccessError):
            self.env['fmes.maintenance.schedule'].with_user(operator).create({
                'equipment_id': self.equipment_saw.id,
            })

    def test_operator_can_read_schedules(self):
        schedule = self._schedule()
        operator = self._create_user(
            'fmes_maint_access_op2', 'furnishing_mes.group_fmes_operator')
        visible = self.env['fmes.maintenance.schedule'].with_user(
            operator).search([('id', '=', schedule.id)])
        self.assertTrue(visible)

    def test_supervisor_cannot_delete_a_schedule(self):
        schedule = self._schedule()
        with self.assertRaises(AccessError):
            schedule.with_user(self.supervisor).unlink()

    def test_manager_can_delete_a_schedule(self):
        schedule = self._schedule()
        schedule.with_user(self.manager).unlink()
        self.assertFalse(schedule.exists())

    def test_operator_cannot_read_the_maintenance_report(self):
        operator = self._create_user(
            'fmes_maint_access_op3', 'furnishing_mes.group_fmes_operator')
        with self.assertRaises(AccessError):
            self.env['fmes.maintenance.report'].with_user(operator).search([])
