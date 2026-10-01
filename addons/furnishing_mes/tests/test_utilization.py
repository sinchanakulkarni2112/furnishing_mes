# -*- coding: utf-8 -*-
"""Phase 6 tests: machine utilisation and OEE (Requirement 5, 3.6).

Three things matter most here. The `fmes.utilization.report` SQL view must
reduce multiple rows correctly (sum, then divide — D0.7), not average
percentages. `_fmes_sync_productive_time` must mirror approved run hours into
a real productive-time log so Odoo's own `mrp.workcenter.oee` finally reads a
non-zero value (D5.6) — the whole reason this deliverable exists. And the
under-utilised / bottleneck service must be a deterministic, batch-efficient
read of that same view, not a per-machine loop.
"""

from datetime import date, datetime, timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import FmesTestCase

REFERENCE_DATE = '2026-01-05'


class UtilizationCase(FmesTestCase):
    """Fixture plant plus one released, approvable production entry."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supervisor = cls._create_user(
            'fmes_util_sup', 'furnishing_mes.group_fmes_supervisor')

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

    def _downtime(self, entry, loss, minutes, start_hour=8):
        """A closed, approved downtime event pinned to REFERENCE_DATE, so it
        lands in the same date/shift/machine grain as `entry`."""
        start = datetime.combine(
            date.fromisoformat(REFERENCE_DATE), datetime.min.time()
        ) + timedelta(hours=start_hour)
        event = self.env['mrp.workcenter.productivity'].create({
            'workcenter_id': entry.workcenter_id.id,
            'loss_id': loss.id,
            'fmes_entry_id': entry.id,
            'date_start': start,
            'date_end': start + timedelta(minutes=minutes),
        })
        event.with_user(self.supervisor).action_approve()
        return event

    def _report_row(self, workcenter=None):
        self.env.flush_all()
        return self.env['fmes.utilization.report'].search([
            ('workcenter_id', '=', (workcenter or self.wc_saw).id),
            ('date', '=', REFERENCE_DATE),
            ('shift_id', '=', self.shift_a.id),
        ])


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase6')
class TestUtilizationReportAggregation(UtilizationCase):
    """The SQL view's own maths, against a fixture shift (7.5 net hours)."""

    def test_only_approved_production_appears(self):
        entry = self._entry(run_hours=2.0, actual_qty=90.0)
        entry.action_submit()
        self.env.flush_all()
        self.assertFalse(
            self._report_row(),
            "A submitted-but-not-approved entry must not feed the report")
        entry.with_user(self.supervisor).action_approve()
        self.assertTrue(self._report_row())

    def test_utilization_pct_is_run_over_available(self):
        entry = self._approve(self._entry(run_hours=2.0, actual_qty=90.0))
        row = self._report_row()
        self.assertAlmostEqual(row.available_hours, 7.5, delta=0.01)
        self.assertAlmostEqual(row.run_hours, 2.0, delta=0.01)
        self.assertAlmostEqual(row.utilization_pct, 2.0 / 7.5 * 100.0,
                               delta=0.5)

    def test_performance_quality_and_oee_formulas(self):
        # product_panel: 48/hr standard rate (fixture capacity matrix).
        entry = self._approve(self._entry(
            run_hours=2.0, actual_qty=90.0, rejected_qty=5.0))
        row = self._report_row()
        std = 48.0 * 2.0  # 96.0
        self.assertAlmostEqual(row.std_output_qty, std, delta=0.01)
        expected_performance = 90.0 / std
        expected_quality = 85.0 / 90.0  # ok_qty / actual_qty
        self.assertAlmostEqual(row.performance, expected_performance,
                               delta=0.001)
        self.assertAlmostEqual(row.quality, expected_quality, delta=0.001)
        self.assertAlmostEqual(row.availability, 1.0, delta=0.001,
                               msg="No downtime logged: availability is 100%")
        expected_oee = (row.availability * expected_performance
                        * expected_quality * 100.0)
        self.assertAlmostEqual(row.oee_pct, expected_oee, delta=0.5)
        self.assertAlmostEqual(row.efficiency_pct,
                               expected_performance * 100.0, delta=0.5)

    def test_unplanned_downtime_reduces_availability_not_planned(self):
        entry = self._approve(self._entry(run_hours=2.0, actual_qty=90.0))
        unplanned = self.env.ref('furnishing_mes.loss_material_handling')
        self._downtime(entry, unplanned, minutes=30, start_hour=8)
        row = self._report_row()
        self.assertAlmostEqual(row.unplanned_downtime_hours, 0.5, delta=0.05)
        expected_availability = (7.5 - 0.5) / 7.5
        self.assertAlmostEqual(row.availability, expected_availability,
                               delta=0.01)

    def test_planned_downtime_does_not_reduce_availability(self):
        entry = self._approve(self._entry(run_hours=2.0, actual_qty=90.0))
        planned = self.env.ref('furnishing_mes.loss_planned_maintenance')
        self._downtime(entry, planned, minutes=30, start_hour=8)
        row = self._report_row()
        self.assertAlmostEqual(row.planned_downtime_hours, 0.5, delta=0.05)
        self.assertAlmostEqual(row.unplanned_downtime_hours, 0.0, delta=0.01)
        self.assertAlmostEqual(row.availability, 1.0, delta=0.01,
                               msg="A planned stoppage must not count "
                                   "against availability")

    def test_idle_hours_is_the_unaccounted_remainder(self):
        entry = self._approve(self._entry(run_hours=2.0, actual_qty=90.0))
        unplanned = self.env.ref('furnishing_mes.loss_material_handling')
        self._downtime(entry, unplanned, minutes=30, start_hour=8)
        row = self._report_row()
        self.assertAlmostEqual(row.idle_hours, 7.5 - 2.0 - 0.5, delta=0.05)

    def test_sum_then_divide_across_multiple_rates(self):
        """D0.7: two products at different capacity rates, in the same
        date/shift/machine (the unique constraint is per product, so both
        can coexist), must reduce to SUM(actual)/SUM(std) — not an average
        of two per-row percentages, which would weight them equally
        regardless of how much each actually produced."""
        # product_wardrobe: category rate 10/hr (walked up from
        # categ_wardrobe to categ_furniture) x 1hr = 10 std, 8 actual.
        self._approve(self._entry(
            product=self.product_wardrobe, run_hours=1.0, actual_qty=8.0))
        # product_panel: product-specific rate 48/hr x 0.5hr = 24 std,
        # 20 actual.
        self._approve(self._entry(
            product=self.product_panel, run_hours=0.5, actual_qty=20.0))

        row = self._report_row()
        self.assertEqual(len(row), 1,
                         "Same date/shift/machine must aggregate into one "
                         "row regardless of how many products were run")
        expected_std = 10.0 + 24.0
        expected_actual = 8.0 + 20.0
        self.assertAlmostEqual(row.std_output_qty, expected_std, delta=0.01)
        self.assertAlmostEqual(row.actual_qty, expected_actual, delta=0.01)
        self.assertAlmostEqual(row.performance,
                               expected_actual / expected_std, delta=0.001)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase6')
class TestSyncProductiveTime(UtilizationCase):
    """Deliverable 8: approval mirrors run_hours into native OEE's input."""

    def test_approval_creates_a_productive_time_log(self):
        entry = self._approve(self._entry(run_hours=3.0, actual_qty=100.0))
        productive_loss = self.env.ref('mrp.block_reason7')
        log = self.env['mrp.workcenter.productivity'].search([
            ('fmes_entry_id', '=', entry.id),
            ('loss_id', '=', productive_loss.id),
        ])
        self.assertEqual(len(log), 1)
        self.assertEqual(log.fmes_state, 'approved')
        self.assertAlmostEqual(log.duration, 3.0 * 60.0, delta=1.0)

    def test_zero_run_hours_creates_no_productive_log(self):
        entry = self._entry(run_hours=0.0, actual_qty=0.0, downtime_hours=1.0)
        self._approve(entry)
        productive_loss = self.env.ref('mrp.block_reason7')
        log = self.env['mrp.workcenter.productivity'].search([
            ('fmes_entry_id', '=', entry.id),
            ('loss_id', '=', productive_loss.id),
        ])
        self.assertFalse(log)

    def test_reopening_removes_the_productive_log(self):
        entry = self._approve(self._entry(run_hours=3.0, actual_qty=100.0))
        manager = self._create_user(
            'fmes_util_mgr', 'furnishing_mes.group_fmes_manager')
        entry.with_user(manager).action_reset_to_draft()
        productive_loss = self.env.ref('mrp.block_reason7')
        log = self.env['mrp.workcenter.productivity'].search([
            ('fmes_entry_id', '=', entry.id),
            ('loss_id', '=', productive_loss.id),
        ])
        self.assertFalse(log,
                         "A reopened entry must not leave phantom "
                         "productive hours behind in native OEE")

    def test_reapproval_updates_rather_than_duplicates_the_log(self):
        entry = self._approve(self._entry(run_hours=2.0, actual_qty=80.0))
        manager = self._create_user(
            'fmes_util_mgr2', 'furnishing_mes.group_fmes_manager')
        entry.with_user(manager).action_reset_to_draft()
        entry.run_hours = 4.0
        self._approve(entry)
        productive_loss = self.env.ref('mrp.block_reason7')
        logs = self.env['mrp.workcenter.productivity'].search([
            ('fmes_entry_id', '=', entry.id),
            ('loss_id', '=', productive_loss.id),
        ])
        self.assertEqual(len(logs), 1)
        self.assertAlmostEqual(logs.duration, 4.0 * 60.0, delta=1.0)

    def test_native_oee_reads_nonzero_once_run_hours_is_mirrored(self):
        """The literal deliverable-9 requirement: before this mirror
        existed, every machine's OEE was permanently 0% because the
        productive side of Odoo's own ratio was never written (D5.6)."""
        today = fields.Date.context_today(self.env['mrp.workcenter'])
        entry = self._entry(
            workcenter=self.wc_edge, date=today, run_hours=3.0,
            actual_qty=100.0)
        entry.action_submit()
        self.wc_edge.invalidate_recordset(['oee'])
        self.assertEqual(
            self.wc_edge.oee, 0.0,
            "Before approval, nothing productive has been logged yet")

        entry.with_user(self.supervisor).action_approve()
        self.wc_edge.invalidate_recordset(['oee'])
        self.assertGreater(
            self.wc_edge.oee, 0.0,
            "Native OEE must read a real value once the approved entry's "
            "run hours are mirrored into a productive-time log")


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase6')
class TestUnderUtilizedAndBottleneck(UtilizationCase):
    """The rolling service behind the machine card, the under-utilised
    list, and the bottleneck suggestion action. Uses dates near the real
    "today" rather than the fixed fixture date, since the service's rolling
    window is `fields.Date.context_today()`-relative (matching Odoo's own
    native OEE window), not tied to any single fixture day.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env['fmes.utilization.service']
        recent = fields.Date.context_today(cls.env['mrp.workcenter'])

        # wc_saw: barely used -> under-utilised.
        cls._approve_at(cls.wc_saw, recent - timedelta(days=1),
                        run_hours=1.0, actual_qty=10.0)
        # wc_spray: middling -> also under-utilised, but less severely.
        cls._approve_at(cls.wc_spray, recent - timedelta(days=1),
                        run_hours=3.0, actual_qty=30.0)
        # wc_edge: heavily loaded -> bottleneck candidate.
        cls._approve_at(cls.wc_edge, recent - timedelta(days=1),
                        run_hours=7.2, actual_qty=70.0)

    @classmethod
    def _approve_at(cls, workcenter, day, run_hours, actual_qty):
        entry = cls.env['fmes.production.entry'].create({
            'date': day,
            'shift_id': cls.shift_a.id,
            'workcenter_id': workcenter.id,
            'product_id': cls.product_panel.id,
            'planned_qty': 100.0,
            'run_hours': run_hours,
            'actual_qty': actual_qty,
        })
        entry.action_submit()
        entry.with_user(cls.supervisor).action_approve()
        return entry

    def setUp(self):
        super().setUp()
        # The fixture entries above were approved in setUpClass; the SQL
        # view reads the underlying tables directly, so pending ORM writes
        # must be flushed before any test here queries it (a raw view read
        # does not trigger the same auto-flush a regular model search does).
        self.env.flush_all()

    def test_workcenter_field_reflects_the_rolling_service(self):
        self.wc_saw.invalidate_recordset(
            ['fmes_utilization_pct', 'fmes_is_under_utilized'])
        self.assertLess(self.wc_saw.fmes_utilization_pct, 60.0)
        self.assertTrue(self.wc_saw.fmes_is_under_utilized)

        self.wc_edge.invalidate_recordset(
            ['fmes_utilization_pct', 'fmes_is_under_utilized'])
        self.assertGreaterEqual(self.wc_edge.fmes_utilization_pct, 90.0)
        self.assertFalse(self.wc_edge.fmes_is_under_utilized)

    def test_under_utilized_machines_worst_first(self):
        under = self.service._under_utilized_machines(self.workcenters)
        under_wcs = [wc for wc, _pct in under]
        self.assertIn(self.wc_saw, under_wcs)
        self.assertIn(self.wc_spray, under_wcs)
        self.assertNotIn(self.wc_edge, under_wcs)
        self.assertLess(under_wcs.index(self.wc_saw),
                        under_wcs.index(self.wc_spray),
                        "The least-utilised machine must sort first")

    def test_rank_by_utilization_highest_first(self):
        ranked = self.service._rank_by_utilization(self.workcenters)
        ranked_wcs = [wc for wc, _pct in ranked]
        self.assertEqual(ranked_wcs[0], self.wc_edge,
                         "The most heavily loaded machine ranks first")
        self.assertEqual(ranked_wcs[-1], self.wc_saw,
                         "The least-utilised machine ranks last")

    def test_suggest_bottlenecks_flags_and_clears_deterministically(self):
        self.assertTrue(self.wc_spray.fmes_is_bottleneck,
                        "Fixture starts wc_spray flagged by hand")
        self.assertFalse(self.wc_edge.fmes_is_bottleneck)

        flagged, cleared = self.service._suggest_bottlenecks(self.workcenters)

        self.assertIn(self.wc_edge, flagged,
                     "A machine at/above the bottleneck threshold must be "
                     "flagged")
        self.assertIn(self.wc_spray, cleared,
                     "A previously-flagged machine below threshold must be "
                     "cleared")
        self.assertNotIn(self.wc_saw, flagged)
        self.assertNotIn(self.wc_saw, cleared)
        self.assertTrue(self.wc_edge.fmes_is_bottleneck)
        self.assertFalse(self.wc_spray.fmes_is_bottleneck)

    def test_action_returns_a_client_notification(self):
        result = self.workcenters.action_fmes_suggest_bottlenecks()
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase6')
class TestUtilizationReportAccess(UtilizationCase):

    def test_operator_cannot_read_the_utilization_report(self):
        operator = self._create_user(
            'fmes_util_op', 'furnishing_mes.group_fmes_operator')
        with self.assertRaises(AccessError):
            self.env['fmes.utilization.report'].with_user(
                operator).search([])

    def test_supervisor_can_read_the_utilization_report(self):
        self._approve(self._entry(run_hours=2.0, actual_qty=90.0))
        self.env.flush_all()
        rows = self.env['fmes.utilization.report'].with_user(
            self.supervisor).search([])
        self.assertTrue(rows)
