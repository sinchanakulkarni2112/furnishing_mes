# -*- coding: utf-8 -*-
"""Phase 10 tests: the production report and the Executive Dashboard service.

The one thing that matters most here (deliverable 7): every figure
`fmes.dashboard.service` returns must equal the same figure computed by
hand from the underlying report models it reads — the dashboard is a thin
aggregator, and a test that only checks "some number came back" would miss
exactly the kind of averaging-instead-of-summing bug D0.7 exists to prevent.

A raw SQL view does not get the ORM's usual auto-flush before `search()`
(D6.1) — every test here that writes through the ORM and then reads
`fmes.production.report` calls `self.env.flush_all()` first.
"""

from datetime import date, datetime, timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import FmesTestCase

REFERENCE_DATE = '2026-01-05'


class DashboardCase(FmesTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supervisor = cls._create_user(
            'fmes_dash_sup', 'furnishing_mes.group_fmes_supervisor')
        cls.service = cls.env['fmes.dashboard.service']

    @classmethod
    def _entry(cls, workcenter=None, shift=None, product=None, **vals):
        base = {
            'date': REFERENCE_DATE,
            'shift_id': (shift or cls.shift_a).id,
            'workcenter_id': (workcenter or cls.wc_saw).id,
            'product_id': (product or cls.product_panel).id,
            'planned_qty': 100.0,
        }
        base.update(vals)
        return cls.env['fmes.production.entry'].create(base)

    def _approve(self, entry):
        entry.action_submit()
        entry.with_user(self.supervisor).action_approve()
        return entry

    def _downtime(self, entry, loss, minutes, start_hour=8, **extra):
        start = datetime.combine(
            date.fromisoformat(REFERENCE_DATE), datetime.min.time()
        ) + timedelta(hours=start_hour)
        vals = {
            'workcenter_id': entry.workcenter_id.id,
            'loss_id': loss.id,
            'fmes_entry_id': entry.id,
            'date_start': start,
            'date_end': start + timedelta(minutes=minutes),
        }
        vals.update(extra)
        event = self.env['mrp.workcenter.productivity'].create(vals)
        event.with_user(self.supervisor).action_approve()
        return event


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase10')
class TestProductionReport(DashboardCase):

    def test_only_approved_entries_appear(self):
        entry = self._entry(run_hours=2.0, actual_qty=90.0)
        entry.action_submit()
        self.env.flush_all()
        rows = self.env['fmes.production.report'].search([
            ('workcenter_id', '=', self.wc_saw.id),
            ('date', '=', REFERENCE_DATE)])
        self.assertFalse(rows)
        entry.with_user(self.supervisor).action_approve()
        self.env.flush_all()
        rows = self.env['fmes.production.report'].search([
            ('workcenter_id', '=', self.wc_saw.id),
            ('date', '=', REFERENCE_DATE)])
        self.assertTrue(rows)

    def test_achievement_and_efficiency_formulas(self):
        self._approve(self._entry(
            product=self.product_panel, run_hours=2.0, actual_qty=90.0,
            rejected_qty=5.0))
        self.env.flush_all()
        row = self.env['fmes.production.report'].search([
            ('workcenter_id', '=', self.wc_saw.id),
            ('date', '=', REFERENCE_DATE)])
        self.assertEqual(len(row), 1)
        self.assertAlmostEqual(row.achievement_pct, 90.0, delta=0.01)
        self.assertEqual(row.ok_qty, 85.0)
        # product_panel: 48/hr standard rate (fixture capacity matrix).
        self.assertAlmostEqual(row.efficiency_pct, 90.0 / 96.0 * 100.0,
                               delta=0.01)

    def test_manpower_hours_feeds_productivity(self):
        self._approve(self._entry(
            run_hours=2.0, actual_qty=90.0, actual_manpower=2.0))
        self.env.flush_all()
        row = self.env['fmes.production.report'].search([
            ('workcenter_id', '=', self.wc_saw.id),
            ('date', '=', REFERENCE_DATE)])
        # shift_a net_hours = 7.5.
        self.assertAlmostEqual(row.manpower_hours, 2.0 * 7.5, delta=0.01)

    def test_grain_keeps_different_products_as_separate_rows(self):
        """Unlike `fmes.utilization.report` (no product dimension), this
        view's own grain includes product_id, so two products in the same
        date/shift/machine are two rows, not one combined row — matching
        the entry-level uniqueness constraint, which already guarantees at
        most one approved entry per (date, shift, machine, product)."""
        self._approve(self._entry(
            product=self.product_wardrobe, run_hours=1.0, actual_qty=8.0))
        self._approve(self._entry(
            product=self.product_panel, run_hours=0.5, actual_qty=20.0))
        self.env.flush_all()
        rows = self.env['fmes.production.report'].search([
            ('workcenter_id', '=', self.wc_saw.id),
            ('date', '=', REFERENCE_DATE)])
        self.assertEqual(len(rows), 2)
        self.assertEqual(set(rows.mapped('product_id')),
                         {self.product_wardrobe, self.product_panel})


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase10')
class TestDashboardKpis(DashboardCase):
    """Deliverable 7: every KPI must match a hand-aggregation of the same
    underlying report rows the service itself reads."""

    def setUp(self):
        super().setUp()
        self._approve(self._entry(
            workcenter=self.wc_saw, product=self.product_panel,
            run_hours=5.0, actual_qty=80.0, rejected_qty=5.0,
            actual_manpower=2.0))
        unplanned = self.env.ref('furnishing_mes.loss_material_handling')
        self._downtime(self._entry(
            workcenter=self.wc_edge, shift=self.shift_b, actual_qty=0.0),
            unplanned, minutes=30)
        self.env.flush_all()

    def test_achievement_pct_matches_manual_aggregation(self):
        data = self.service.get_dashboard_data(
            REFERENCE_DATE, REFERENCE_DATE)
        rows = self.env['fmes.production.report'].search([
            ('date', '=', REFERENCE_DATE)])
        manual = (sum(rows.mapped('actual_qty'))
                 / sum(rows.mapped('planned_qty')) * 100.0)
        self.assertAlmostEqual(
            data['kpis']['achievement_pct']['value'], manual, delta=0.1)

    def test_utilization_pct_matches_manual_aggregation(self):
        data = self.service.get_dashboard_data(
            REFERENCE_DATE, REFERENCE_DATE)
        rows = self.env['fmes.utilization.report'].search([
            ('date', '=', REFERENCE_DATE)])
        manual = (sum(rows.mapped('run_hours'))
                 / sum(rows.mapped('available_hours')) * 100.0)
        self.assertAlmostEqual(
            data['kpis']['utilization_pct']['value'], manual, delta=0.1)

    def test_downtime_pct_matches_manual_aggregation(self):
        data = self.service.get_dashboard_data(
            REFERENCE_DATE, REFERENCE_DATE)
        rows = self.env['fmes.utilization.report'].search([
            ('date', '=', REFERENCE_DATE)])
        downtime = (sum(rows.mapped('unplanned_downtime_hours'))
                   + sum(rows.mapped('planned_downtime_hours')))
        manual = downtime / sum(rows.mapped('available_hours')) * 100.0
        self.assertAlmostEqual(
            data['kpis']['downtime_pct']['value'], manual, delta=0.1)

    def test_oee_pct_matches_manual_aggregation(self):
        data = self.service.get_dashboard_data(
            REFERENCE_DATE, REFERENCE_DATE)
        rows = self.env['fmes.utilization.report'].search([
            ('date', '=', REFERENCE_DATE)])
        available = sum(rows.mapped('available_hours'))
        unplanned = sum(rows.mapped('unplanned_downtime_hours'))
        std_output = sum(rows.mapped('std_output_qty'))
        actual = sum(rows.mapped('actual_qty'))
        ok = sum(rows.mapped('ok_qty'))
        availability = (available - unplanned) / available
        performance = actual / std_output
        quality = ok / actual
        manual = availability * performance * quality * 100.0
        self.assertAlmostEqual(
            data['kpis']['oee_pct']['value'], manual, delta=0.1)

    def test_kpi_tile_carries_target_and_direction(self):
        data = self.service.get_dashboard_data(
            REFERENCE_DATE, REFERENCE_DATE)
        self.assertEqual(data['kpis']['achievement_pct']['target'], 95.0)
        self.assertTrue(data['kpis']['achievement_pct']['higher_is_better'])
        self.assertEqual(data['kpis']['downtime_pct']['target'], 10.0)
        self.assertFalse(data['kpis']['downtime_pct']['higher_is_better'])

    def test_previous_period_is_a_separate_equal_length_window(self):
        data = self.service.get_dashboard_data(
            REFERENCE_DATE, REFERENCE_DATE)
        # Nothing approved the day before, so the previous period reads 0
        # while the current period (this fixture's own entry) does not.
        self.assertEqual(data['kpis']['achievement_pct']['previous'], 0.0)
        self.assertGreater(data['kpis']['achievement_pct']['value'], 0.0)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase10')
class TestDashboardTiles(DashboardCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def _production_rows(self):
        self.env.flush_all()
        return self.service._fetch_production_rows(
            date.fromisoformat(REFERENCE_DATE),
            date.fromisoformat(REFERENCE_DATE),
            self.env['hr.department'], self.env.company)

    def _utilization_rows(self):
        self.env.flush_all()
        return self.service._fetch_utilization_rows(
            date.fromisoformat(REFERENCE_DATE),
            date.fromisoformat(REFERENCE_DATE),
            self.env['hr.department'], self.env.company)

    def test_production_trend_grouped_by_date(self):
        self._approve(self._entry(run_hours=1.0, actual_qty=50.0))
        trend = self.service._production_trend(self._production_rows())
        self.assertEqual(len(trend), 1)
        self.assertEqual(trend[0]['date'], REFERENCE_DATE)
        self.assertEqual(trend[0]['actual_qty'], 50.0)

    def test_downtime_pareto_is_sorted_with_cumulative_pct(self):
        entry = self._entry(actual_qty=0.0)
        material = self.env.ref('furnishing_mes.loss_material_handling')
        other = self.env.ref('furnishing_mes.loss_other')
        self._downtime(entry, material, minutes=40)
        self._downtime(self._entry(
            workcenter=self.wc_edge, shift=self.shift_b, actual_qty=0.0),
            other, minutes=20, start_hour=9, fmes_remarks='note')
        self.env.flush_all()
        pareto = self.service._downtime_pareto(
            date.fromisoformat(REFERENCE_DATE),
            date.fromisoformat(REFERENCE_DATE),
            self.env['hr.department'], self.env.company)
        self.assertEqual(len(pareto), 2)
        self.assertGreaterEqual(pareto[0]['hours'], pareto[1]['hours'])
        self.assertAlmostEqual(pareto[-1]['cumulative_pct'], 100.0, delta=0.5)

    def test_department_performance_groups_by_department(self):
        self._approve(self._entry(
            workcenter=self.wc_saw, run_hours=1.0, actual_qty=10.0))
        self._approve(self._entry(
            workcenter=self.wc_spray, shift=self.shift_b, run_hours=1.0,
            actual_qty=5.0, planned_qty=50.0))
        rows = self.service._department_performance(self._production_rows())
        depts = {r['department'] for r in rows}
        self.assertIn(self.dept_cutting.name, depts)
        self.assertIn(self.dept_finishing.name, depts)

    def test_machine_ranking_flags_under_utilized(self):
        self._approve(self._entry(
            workcenter=self.wc_saw, run_hours=0.5, actual_qty=5.0))
        rows = self.service._machine_utilization_ranking(
            self._utilization_rows())
        saw_row = next(r for r in rows if r['machine'] == self.wc_saw.display_name)
        self.assertTrue(saw_row['is_under_utilized'])

    def test_backlog_ageing_buckets_the_latest_snapshot(self):
        Snapshot = self.env['fmes.backlog.snapshot']
        Snapshot.create({
            'snapshot_date': REFERENCE_DATE,
            'product_id': self.product_wardrobe.id,
            'department_id': self.dept_cutting.id,
            'pending_qty': 40.0, 'days_delayed': 5, 'status': 'delayed',
            'company_id': self.company.id,
        })
        buckets = self.service._backlog_ageing(
            self.env['hr.department'], self.company)
        bucket_4_7 = next(b for b in buckets if b['bucket'] == '4-7')
        self.assertEqual(bucket_4_7['pending_qty'], 40.0)

    def test_maintenance_performance_reads_native_equipment_fields(self):
        result = self.service._maintenance_performance(
            date.fromisoformat(REFERENCE_DATE),
            date.fromisoformat(REFERENCE_DATE),
            self.env['hr.department'], self.env.company)
        self.assertIn('mtbf', result)
        self.assertIn('mttr', result)
        self.assertIn('pm_compliance_pct', result)
        self.assertIn('open_breakdowns', result)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase10')
class TestDashboardAndProductionReportSecurity(DashboardCase):

    def test_operator_cannot_read_the_production_report(self):
        operator = self._create_user(
            'fmes_dash_op', 'furnishing_mes.group_fmes_operator')
        with self.assertRaises(AccessError):
            self.env['fmes.production.report'].with_user(
                operator).search([])

    def test_supervisor_with_assigned_department_is_scoped(self):
        supervisor = self._create_user(
            'fmes_dash_sup2', 'furnishing_mes.group_fmes_supervisor')
        supervisor.fmes_department_ids = [(6, 0, [self.dept_cutting.id])]
        self._approve(self._entry(workcenter=self.wc_saw, run_hours=1.0,
                                  actual_qty=10.0))
        self._approve(self._entry(workcenter=self.wc_spray,
                                  shift=self.shift_b, run_hours=1.0,
                                  actual_qty=10.0, planned_qty=50.0))
        self.env.flush_all()
        visible = self.env['fmes.production.report'].with_user(
            supervisor).search([('date', '=', REFERENCE_DATE)])
        self.assertTrue(
            all(row.department_id == self.dept_cutting for row in visible))

    def test_manager_sees_every_department(self):
        manager = self._create_user(
            'fmes_dash_mgr', 'furnishing_mes.group_fmes_manager')
        self._approve(self._entry(workcenter=self.wc_spray,
                                  shift=self.shift_b, run_hours=1.0,
                                  actual_qty=10.0, planned_qty=50.0))
        self.env.flush_all()
        visible = self.env['fmes.production.report'].with_user(
            manager).search([('date', '=', REFERENCE_DATE)])
        self.assertTrue(visible)

    def test_dashboard_service_respects_department_scoping(self):
        """A department-scoped supervisor calling the dashboard directly
        must not see figures from a department they are not assigned to,
        even without an explicit department_ids filter — the underlying
        report queries run under their own record rules."""
        supervisor = self._create_user(
            'fmes_dash_sup3', 'furnishing_mes.group_fmes_supervisor')
        supervisor.fmes_department_ids = [(6, 0, [self.dept_cutting.id])]
        self._approve(self._entry(workcenter=self.wc_spray,
                                  shift=self.shift_b, run_hours=1.0,
                                  actual_qty=10.0, planned_qty=50.0))
        self.env.flush_all()
        data = self.env['fmes.dashboard.service'].with_user(
            supervisor).get_dashboard_data(REFERENCE_DATE, REFERENCE_DATE)
        depts = {r['department'] for r in data['department_performance']}
        self.assertNotIn(self.dept_finishing.name, depts)
