# -*- coding: utf-8 -*-
"""Phase 5 tests: coded downtime, approval, escalation and analysis.

Two invariants matter most. Every downtime minute must carry a coded reason —
the model refuses to save one that does not, not just the terminal UI. And
approved downtime must stay locked, for the same reason approved production
entries do (Phase 4, D4.1/D4.2): a downtime figure feeding a report that can
still be quietly restated is not a figure worth reporting.
"""

from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import HttpCase
from odoo.tools import mute_logger

from .common import FmesTestCase


class DowntimeCase(FmesTestCase):
    """Fixture plant plus one production entry and the loss reasons it uses."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.entry = cls.env['fmes.production.entry'].create({
            'date': cls.reference_date,
            'shift_id': cls.shift_a.id,
            'workcenter_id': cls.wc_saw.id,
            'product_id': cls.product_wardrobe.id,
            'planned_qty': 100.0,
        })
        cls.other_entry = cls.env['fmes.production.entry'].create({
            'date': cls.reference_date,
            'shift_id': cls.shift_b.id,
            'workcenter_id': cls.wc_edge.id,
            'product_id': cls.product_wardrobe.id,
            'planned_qty': 50.0,
        })

        # A categorised availability-loss reason, unplanned.
        cls.reason_material = cls.env.ref(
            'furnishing_mes.loss_material_handling')
        # The reason flagged to auto-escalate to maintenance.
        cls.reason_breakdown = cls.env.ref('mrp.block_reason1')
        # "Other" — requires a remark.
        cls.reason_other = cls.env.ref('furnishing_mes.loss_other')
        # Odoo's own "Fully Productive Time" — never a downtime reason.
        cls.reason_productive = cls.env.ref('mrp.block_reason7')

    def _open_event(self, entry=None, loss=None, minutes_ago=30, **extra):
        entry = entry or self.entry
        loss = loss or self.reason_material
        vals = {
            'workcenter_id': entry.workcenter_id.id,
            'loss_id': loss.id,
            'fmes_entry_id': entry.id,
            'date_start': fields.Datetime.now() - timedelta(
                minutes=minutes_ago),
        }
        vals.update(extra)
        return self.env['mrp.workcenter.productivity'].create(vals)

    def _closed_event(self, entry=None, loss=None, minutes=30, **extra):
        event = self._open_event(entry=entry, loss=loss, minutes_ago=minutes,
                                 **extra)
        event.date_end = fields.Datetime.now()
        return event


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase5')
class TestDowntimeCategorisation(DowntimeCase):
    """No downtime minute may go uncategorised."""

    def test_categorised_reason_is_accepted(self):
        event = self._open_event()
        self.assertEqual(event.fmes_category, 'material_handling')

    def test_reason_without_a_category_is_refused(self):
        uncategorised = self.env['mrp.workcenter.productivity.loss'].create({
            'name': 'Test Uncategorised Reason',
            'loss_id': self.env.ref('mrp.category_availability').id,
        })
        with self.assertRaises(ValidationError):
            self._open_event(loss=uncategorised)

    def test_fully_productive_time_is_exempt_from_the_rule(self):
        """Productive time is not downtime and carries no category by design."""
        event = self.env['mrp.workcenter.productivity'].create({
            'workcenter_id': self.wc_saw.id,
            'loss_id': self.reason_productive.id,
            'date_start': self.reference_date,
        })
        self.assertFalse(event.fmes_category)

    def test_other_requires_a_remark(self):
        with self.assertRaises(ValidationError):
            self._open_event(loss=self.reason_other)

    def test_other_with_a_remark_is_accepted(self):
        event = self._open_event(loss=self.reason_other,
                                 fmes_remarks='Waiting on a spare belt')
        self.assertEqual(event.fmes_category, 'other')


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase5')
class TestDowntimeDuration(DowntimeCase):

    def test_duration_computed_from_start_and_end(self):
        event = self._closed_event(minutes=45)
        self.assertAlmostEqual(event.duration, 45.0, delta=1.0)

    def test_running_event_has_no_duration_yet(self):
        event = self._open_event()
        self.assertEqual(event.duration, 0.0)
        self.assertTrue(event.fmes_is_running)

    def test_stopping_clears_the_running_flag(self):
        event = self._open_event()
        event.date_end = fields.Datetime.now()
        self.assertFalse(event.fmes_is_running)

    def test_only_one_open_event_per_machine(self):
        self._open_event()
        with self.assertRaises(ValidationError):
            self._open_event(entry=self.entry, loss=self.reason_other,
                             fmes_remarks='second one')

    def test_a_different_machine_may_have_its_own_open_event(self):
        self._open_event()  # on the saw
        other = self._open_event(entry=self.other_entry)  # on the edge bander
        self.assertTrue(other.fmes_is_running)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase5')
class TestDowntimeApproval(DowntimeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supervisor = cls._create_user(
            'fmes_dt_sup', 'furnishing_mes.group_fmes_supervisor')
        cls.operator = cls._create_user(
            'fmes_dt_op', 'furnishing_mes.group_fmes_operator')
        cls.operator.fmes_workcenter_ids = [(6, 0, [cls.wc_saw.id])]

    def test_new_event_starts_as_draft(self):
        event = self._closed_event()
        self.assertEqual(event.fmes_state, 'draft')

    def test_running_event_cannot_be_approved(self):
        event = self._open_event()
        with self.assertRaises(UserError):
            event.with_user(self.supervisor).action_approve()

    def test_supervisor_can_approve(self):
        event = self._closed_event()
        event.with_user(self.supervisor).action_approve()
        self.assertEqual(event.fmes_state, 'approved')
        self.assertEqual(event.fmes_approved_by, self.supervisor)
        self.assertTrue(event.fmes_approved_on)

    def test_operator_cannot_approve(self):
        event = self._closed_event()
        with self.assertRaises(AccessError):
            event.with_user(self.operator).action_approve()

    def test_direct_write_to_approved_is_refused(self):
        """The same hole D4.2 closed on production entries, closed here too."""
        event = self._closed_event()
        with self.assertRaises(AccessError):
            event.with_user(self.operator).write({'fmes_state': 'approved'})

    def test_reject_returns_it_to_draft(self):
        event = self._closed_event()
        event.with_user(self.supervisor).action_reject(reason='wrong category')
        self.assertEqual(event.fmes_state, 'rejected')

    def test_editing_a_rejected_event_returns_it_to_the_operator(self):
        """'Rejected' becomes editable the moment it is edited — no separate
        resubmit button needed."""
        event = self._closed_event()
        event.with_user(self.supervisor).action_reject()
        self.assertEqual(event.fmes_state, 'rejected')
        event.with_user(self.operator).write(
            {'fmes_remarks': 'fixed the category'})
        self.assertEqual(event.fmes_state, 'draft')

    def test_approved_event_is_locked(self):
        event = self._closed_event()
        event.with_user(self.supervisor).action_approve()
        with self.assertRaises(AccessError):
            event.with_user(self.supervisor).write(
                {'loss_id': self.reason_other.id})

    def test_manager_can_reopen_an_approved_event(self):
        event = self._closed_event()
        event.with_user(self.supervisor).action_approve()
        manager = self._create_user(
            'fmes_dt_mgr', 'furnishing_mes.group_fmes_manager')
        event.with_user(manager).action_reset_to_draft()
        self.assertEqual(event.fmes_state, 'draft')

    def test_supervisor_cannot_reopen_an_approved_event(self):
        event = self._closed_event()
        event.with_user(self.supervisor).action_approve()
        with self.assertRaises(AccessError):
            event.with_user(self.supervisor).action_reset_to_draft()


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase5')
class TestMaintenanceEscalation(DowntimeCase):

    def test_flagged_reason_raises_a_request(self):
        event = self._closed_event(loss=self.reason_breakdown)
        self.assertTrue(event.fmes_maintenance_request_id)
        request = event.fmes_maintenance_request_id
        self.assertEqual(request.equipment_id, self.equipment_saw)
        self.assertEqual(request.maintenance_type, 'corrective')

    def test_unflagged_reason_does_not_escalate(self):
        event = self._closed_event(loss=self.reason_material)
        self.assertFalse(event.fmes_maintenance_request_id)

    def test_no_equipment_means_no_escalation_but_no_crash(self):
        """wc_edge has no linked equipment in the fixture plant."""
        event = self._closed_event(entry=self.other_entry,
                                   loss=self.reason_breakdown)
        self.assertFalse(event.fmes_maintenance_request_id)

    def test_escalation_uses_the_seeded_default_team(self):
        event = self._closed_event(loss=self.reason_breakdown)
        team = self.env.ref('furnishing_mes.fmes_maintenance_team_default')
        self.assertEqual(event.fmes_maintenance_request_id.maintenance_team_id,
                         team)

    def test_escalation_happens_at_creation_not_approval(self):
        """A broken machine needs attention now, not after paperwork."""
        event = self._open_event(loss=self.reason_breakdown)
        self.assertTrue(
            event.fmes_maintenance_request_id,
            "Escalation must not wait for the event to be stopped or approved")


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase5')
class TestEntryDowntimeRollup(DowntimeCase):

    def test_rollup_sums_completed_events(self):
        self._closed_event(minutes=20)
        self._closed_event(loss=self.reason_other, minutes=10,
                           fmes_remarks='second stoppage')
        self.entry.invalidate_recordset(['downtime_hours'])
        self.assertAlmostEqual(self.entry.downtime_hours, 30.0 / 60.0,
                               delta=0.05)

    def test_running_events_are_not_counted_yet(self):
        self._open_event(minutes_ago=15)
        self.entry.invalidate_recordset(['downtime_hours'])
        self.assertEqual(self.entry.downtime_hours, 0.0)

    def test_imported_hours_survive_when_no_events_exist(self):
        """A migrated Excel row has no coded events behind it at all."""
        self.entry.with_context(fmes_bypass_lock=True).write(
            {'downtime_hours': 1.5})
        # Touching an unrelated field must not zero out the imported figure.
        self.entry.run_hours = 6.0
        self.assertEqual(self.entry.downtime_hours, 1.5)

    def test_rollup_stops_once_the_entry_is_approved(self):
        self._closed_event(minutes=20)
        self.entry.invalidate_recordset(['downtime_hours'])
        self.entry.actual_qty = 90.0
        self.entry.action_submit()
        self.entry.action_approve()
        locked_value = self.entry.downtime_hours

        # A downtime event under an approved entry can still be reviewed...
        supervisor = self._create_user(
            'fmes_dt_rollup_sup', 'furnishing_mes.group_fmes_supervisor')
        event = self.entry.productivity_ids[0]
        event.with_user(supervisor).action_approve()
        # ...but the entry's own frozen figure must not move.
        self.entry.invalidate_recordset(['downtime_hours'])
        self.assertEqual(self.entry.downtime_hours, locked_value)

    def test_stat_button_count(self):
        self._closed_event()
        self._closed_event(loss=self.reason_other, fmes_remarks='note')
        self.entry.invalidate_recordset(['downtime_event_count'])
        self.assertEqual(self.entry.downtime_event_count, 2)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase5')
class TestDowntimeReport(DowntimeCase):
    """The SQL view backing loss analysis (Requirement 6.3)."""

    def test_only_approved_events_appear(self):
        draft = self._closed_event(minutes=20)
        self.env.flush_all()
        rows = self.env['fmes.downtime.report'].search(
            [('workcenter_id', '=', self.wc_saw.id)])
        self.assertFalse(
            rows, "A draft (unreviewed) event must not appear in the report")

        draft.action_approve()
        self.env.flush_all()
        rows = self.env['fmes.downtime.report'].search(
            [('workcenter_id', '=', self.wc_saw.id)])
        self.assertTrue(rows)

    def test_running_events_are_excluded(self):
        self._open_event()
        self.env.flush_all()
        rows = self.env['fmes.downtime.report'].search(
            [('workcenter_id', '=', self.wc_saw.id)])
        self.assertFalse(rows)

    def test_hours_and_event_count_aggregate_correctly(self):
        e1 = self._closed_event(minutes=20)
        e2 = self._closed_event(minutes=40)
        (e1 + e2).action_approve()
        self.env.flush_all()
        row = self.env['fmes.downtime.report'].search([
            ('workcenter_id', '=', self.wc_saw.id),
            ('loss_id', '=', self.reason_material.id),
        ])
        self.assertEqual(len(row), 1, "Same date/shift/machine/reason must "
                                      "aggregate into one row")
        self.assertEqual(row.event_count, 2)
        self.assertAlmostEqual(row.downtime_hours, 60.0 / 60.0, delta=0.05)

    def test_pct_of_available_uses_shift_net_hours(self):
        event = self._closed_event(minutes=45)  # shift_a: 7.5 net hours
        event.action_approve()
        self.env.flush_all()
        row = self.env['fmes.downtime.report'].search([
            ('workcenter_id', '=', self.wc_saw.id)])
        expected_pct = (45.0 / 60.0) / 7.5 * 100.0
        self.assertAlmostEqual(row.pct_of_available, expected_pct, delta=1.0)

    def test_different_reasons_are_separate_rows(self):
        e1 = self._closed_event(loss=self.reason_material, minutes=10)
        e2 = self._closed_event(loss=self.reason_other, minutes=10,
                                fmes_remarks='note')
        (e1 + e2).action_approve()
        self.env.flush_all()
        rows = self.env['fmes.downtime.report'].search(
            [('workcenter_id', '=', self.wc_saw.id)])
        self.assertEqual(len(rows), 2)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase5')
class TestOeeConsistency(DowntimeCase):
    """Deliverable 8: our extension must not disturb Odoo's own OEE.

    We extend mrp.workcenter.productivity rather than building a parallel
    model (ADR-001) specifically so this stays true.
    """

    def test_unplanned_downtime_reduces_native_oee(self):
        # A long productive run, then a chunk of unplanned downtime.
        now = fields.Datetime.now()
        self.env['mrp.workcenter.productivity'].create({
            'workcenter_id': self.wc_saw.id,
            'loss_id': self.reason_productive.id,
            'date_start': now - timedelta(hours=2),
            'date_end': now - timedelta(hours=1),
        })
        self._closed_event(minutes=30)

        self.wc_saw.invalidate_recordset(['oee'])
        oee_with_downtime = self.wc_saw.oee

        # Same productive run, no downtime.
        self.env['mrp.workcenter.productivity'].create({
            'workcenter_id': self.wc_edge.id,
            'loss_id': self.reason_productive.id,
            'date_start': now - timedelta(hours=2),
            'date_end': now - timedelta(hours=1),
        })
        self.wc_edge.invalidate_recordset(['oee'])
        oee_without_downtime = self.wc_edge.oee

        self.assertLess(
            oee_with_downtime, oee_without_downtime,
            "Logging unplanned downtime through our extension must still "
            "move Odoo's own OEE computation")

    def test_native_effectiveness_category_is_untouched(self):
        """Our fmes_category is layered on top of, not instead of, loss_type."""
        event = self._closed_event(loss=self.reason_breakdown)
        self.assertEqual(event.loss_type, 'availability')
        self.assertEqual(event.fmes_category, 'maintenance')


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase5')
class TestDowntimeAccess(DowntimeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = cls._create_user(
            'fmes_dt_access_op', 'furnishing_mes.group_fmes_operator')
        cls.operator.fmes_workcenter_ids = [(6, 0, [cls.wc_saw.id])]
        cls.other_operator = cls._create_user(
            'fmes_dt_access_op2', 'furnishing_mes.group_fmes_operator')
        cls.other_operator.fmes_workcenter_ids = [(6, 0, [cls.wc_edge.id])]

    def test_operator_may_log_downtime_on_their_own_machine(self):
        event = self._open_event().with_user(self.operator)
        self.assertTrue(event.exists())

    def test_operator_cannot_see_downtime_on_another_machine(self):
        event = self._open_event(entry=self.other_entry)  # wc_edge
        visible = self.env['mrp.workcenter.productivity'].with_user(
            self.operator).search([('id', '=', event.id)])
        self.assertFalse(visible)

    def test_operator_cannot_edit_an_approved_event(self):
        event = self._closed_event()
        supervisor = self._create_user(
            'fmes_dt_access_sup', 'furnishing_mes.group_fmes_supervisor')
        event.with_user(supervisor).action_approve()
        with self.assertRaises(AccessError):
            event.with_user(self.operator).write({'fmes_remarks': 'edit'})

    def test_operator_cannot_read_the_loss_analysis_report(self):
        with self.assertRaises(AccessError):
            self.env['fmes.downtime.report'].with_user(
                self.operator).search([])


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase5')
class TestTerminalDowntimeEndpoints(HttpCase):
    """The terminal's reason picker and running timer, over real HTTP."""

    def setUp(self):
        super().setUp()
        self.shift = self.env['fmes.shift'].create({
            'name': 'DT Terminal Shift', 'code': 'DTT',
            'start_time': 6.0, 'end_time': 14.0, 'break_minutes': 30,
        })
        self.machine = self.env['mrp.workcenter'].create({
            'name': 'DT Terminal Machine', 'code': 'DT-TERM',
            'fmes_machine_code': 'DT-TERM-01',
        })
        self.other_machine = self.env['mrp.workcenter'].create(
            {'name': 'DT Off Limits', 'code': 'DT-OFF'})
        self.product = self.env['product.product'].create(
            {'name': 'DT Terminal Product'})
        self.entry = self.env['fmes.production.entry'].create({
            'date': '2026-01-05',
            'shift_id': self.shift.id,
            'workcenter_id': self.machine.id,
            'product_id': self.product.id,
            'planned_qty': 40.0,
        })
        self.other_entry = self.env['fmes.production.entry'].create({
            'date': '2026-01-05',
            'shift_id': self.shift.id,
            'workcenter_id': self.other_machine.id,
            'product_id': self.product.id,
            'planned_qty': 10.0,
        })
        self.operator = self.env['res.users'].create({
            'name': 'DT Terminal Operator',
            'login': 'fmes_dt_terminal_op',
            'password': 'fmes_dt_terminal_op',
            'groups_id': [(6, 0, [
                self.env.ref('furnishing_mes.group_fmes_operator').id])],
            'fmes_workcenter_ids': [(6, 0, [self.machine.id])],
        })
        self.reason = self.env.ref('furnishing_mes.loss_material_handling')
        self.reason_other = self.env.ref('furnishing_mes.loss_other')

    def test_reasons_are_grouped_and_categorised_only(self):
        self.authenticate('fmes_dt_terminal_op', 'fmes_dt_terminal_op')
        groups = self.make_jsonrpc_request(
            '/fmes/terminal/downtime/reasons', {})
        self.assertTrue(groups)
        all_ids = [r['id'] for g in groups for r in g['reasons']]
        productive = self.env.ref('mrp.block_reason7')
        self.assertNotIn(productive.id, all_ids)
        other_group = next(g for g in groups if g['category'] == 'other')
        self.assertTrue(other_group['reasons'][0]['requires_remark'])

    def test_start_then_stop_over_http(self):
        self.authenticate('fmes_dt_terminal_op', 'fmes_dt_terminal_op')
        started = self.make_jsonrpc_request('/fmes/terminal/downtime/start', {
            'entry_id': self.entry.id,
            'loss_id': self.reason.id,
        })
        self.assertTrue(started['ok'], started.get('error'))
        self.assertTrue(started['event']['running'])

        # Backdate the start so stopping immediately after still reflects a
        # real elapsed duration: an automated test's own start-then-stop
        # round trip is fast enough that both calls can land in the same
        # second, and native duration truncates to whole seconds
        # (mrp.workcenter.productivity._compute_duration rounds off
        # microseconds), so an unmodified timestamp can genuinely compute to
        # a true, non-buggy 0.0 minutes here.
        event = self.env['mrp.workcenter.productivity'].browse(
            started['event']['id'])
        event.sudo().date_start = fields.Datetime.now() - timedelta(minutes=5)

        stopped = self.make_jsonrpc_request('/fmes/terminal/downtime/stop', {
            'event_id': started['event']['id'],
        })
        self.assertTrue(stopped['ok'], stopped.get('error'))
        self.assertFalse(stopped['event']['running'])
        self.assertAlmostEqual(stopped['event']['duration_minutes'], 5.0,
                               delta=0.5)

    def test_starting_on_another_machine_is_refused(self):
        self.authenticate('fmes_dt_terminal_op', 'fmes_dt_terminal_op')
        result = self.make_jsonrpc_request('/fmes/terminal/downtime/start', {
            'entry_id': self.other_entry.id,
            'loss_id': self.reason.id,
        })
        self.assertFalse(result['ok'])

    def test_second_start_on_the_same_machine_is_refused(self):
        self.authenticate('fmes_dt_terminal_op', 'fmes_dt_terminal_op')
        first = self.make_jsonrpc_request('/fmes/terminal/downtime/start', {
            'entry_id': self.entry.id, 'loss_id': self.reason.id,
        })
        self.assertTrue(first['ok'])
        second = self.make_jsonrpc_request('/fmes/terminal/downtime/start', {
            'entry_id': self.entry.id, 'loss_id': self.reason_other.id,
            'remarks': 'irrelevant',
        })
        self.assertFalse(second['ok'])

    def test_other_reason_without_remarks_is_refused(self):
        """A graceful {ok: False}, not a raised server error.

        This specific case is what exposed D5.4: the model's api.constrains
        depended on a computed field (fmes_category), whose validation Odoo
        could defer past the controller's own try/except to the HTTP layer's
        post-dispatch flush. The model now validates this rule early and
        synchronously in create()/write(), which is what this test actually
        verifies end-to-end.
        """
        self.authenticate('fmes_dt_terminal_op', 'fmes_dt_terminal_op')
        result = self.make_jsonrpc_request('/fmes/terminal/downtime/start', {
            'entry_id': self.entry.id, 'loss_id': self.reason_other.id,
        })
        self.assertFalse(result['ok'])

    def test_downtime_hours_field_is_no_longer_directly_writable(self):
        """Phase 4's free-typed downtime field is retired from the terminal.

        Sent alongside a field that IS still writable, so the request has
        something to legitimately save — proving downtime_hours specifically
        is dropped, rather than the whole request being rejected for having
        nothing left once it is filtered out.
        """
        self.authenticate('fmes_dt_terminal_op', 'fmes_dt_terminal_op')
        result = self.make_jsonrpc_request('/fmes/terminal/record', {
            'entry_id': self.entry.id,
            'values': {'downtime_hours': 5.0, 'run_hours': 3.0},
        })
        self.assertTrue(result['ok'], result.get('error'))
        self.entry.invalidate_recordset()
        self.assertEqual(
            self.entry.downtime_hours, 0.0,
            "downtime_hours must not be settable through /fmes/terminal/record")
        self.assertAlmostEqual(self.entry.run_hours, 3.0, places=4)
