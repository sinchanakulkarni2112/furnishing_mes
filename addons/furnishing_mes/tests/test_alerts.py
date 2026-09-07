# -*- coding: utf-8 -*-
"""Phase 11 tests: the rule-driven alert engine (Requirement 10).

Three things matter most here, mirroring the phase's own design choices.
A rule's threshold comparison must be exact at the boundary (`_compares` is
the single place every alert type shares, so it is tested for all five
operators once rather than per type). Once an alert has fired it must not
fire again for the same (rule, subject) pair while it is still open, nor
again inside its own cooldown window even after it is resolved -- that is
what keeps a plant from getting an alert storm. And severity governs when a
notification actually leaves the building: critical alerts dispatch the
moment they are raised, everything else is queued (`notified_on` stays
unset) for the cron to flush later -- see `services/alert_engine.py`'s own
`_dispatch_queued_notifications` docstring for the 08:00 rule (assumption
A35), which is not itself exercised here since it branches on the real
wall clock and this codebase does not depend on a time-freezing library.
"""

from datetime import datetime, time, timedelta

from odoo import fields
from odoo.tests import tagged

from .common import FmesTestCase


class AlertCase(FmesTestCase):
    """Fixture plant plus a supervisor/manager pair to raise alerts against."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = cls.env['fmes.alert.engine']
        cls.today = fields.Date.context_today(cls.env.user)
        cls.supervisor = cls._create_user(
            'fmes_alert_sup', 'furnishing_mes.group_fmes_supervisor')
        cls.manager = cls._create_user(
            'fmes_alert_mgr', 'furnishing_mes.group_fmes_manager')
        cls.group_supervisor = cls.env.ref('furnishing_mes.group_fmes_supervisor')
        cls.group_manager = cls.env.ref('furnishing_mes.group_fmes_manager')

    @classmethod
    def _rule(cls, **vals):
        base = {
            'name': 'Test Rule',
            'alert_type': 'target_not_achieved',
            'operator': 'lt',
            'threshold': 95.0,
            'threshold_uom': 'percent',
            'severity': 'warning',
            'cooldown_minutes': 60,
        }
        base.update(vals)
        return cls.env['fmes.alert.rule'].create(base)

    def _entry(self, workcenter, planned, actual, **vals):
        base = {
            'date': self.today,
            'shift_id': self.shift_a.id,
            'workcenter_id': workcenter.id,
            'product_id': self.product_wardrobe.id,
            'planned_qty': planned,
            'actual_qty': actual,
        }
        base.update(vals)
        entry = self.env['fmes.production.entry'].create(base)
        entry.action_submit()
        entry.action_approve()
        return entry

    def _downtime_event(self, workcenter, minutes, shift=None, loss_ref='mrp.block_reason1'):
        start = datetime.combine(self.today, time(8, 0))
        return self.env['mrp.workcenter.productivity'].create({
            'workcenter_id': workcenter.id,
            'loss_id': self.env.ref(loss_ref).id,
            'fmes_shift_id': (shift or self.shift_a).id,
            'date_start': start,
            'date_end': start + timedelta(minutes=minutes),
        })


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase11')
class TestRuleOperators(AlertCase):
    """`_compares` is the one place all seven alert types share."""

    def test_all_five_operators_compare_at_the_boundary(self):
        rule = self._rule(operator='gt', threshold=10.0)
        self.assertTrue(rule._compares(10.1))
        self.assertFalse(rule._compares(10.0))

        rule.operator = 'gte'
        self.assertTrue(rule._compares(10.0))
        self.assertFalse(rule._compares(9.9))

        rule.operator = 'lt'
        self.assertTrue(rule._compares(9.9))
        self.assertFalse(rule._compares(10.0))

        rule.operator = 'lte'
        self.assertTrue(rule._compares(10.0))
        self.assertFalse(rule._compares(10.1))

        rule.operator = 'eq'
        self.assertTrue(rule._compares(10.0))
        self.assertFalse(rule._compares(10.1))


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase11')
class TestTargetNotAchieved(AlertCase):
    """`lt` operator, exercised through the real evaluation path."""

    def test_below_threshold_triggers(self):
        rule = self._rule(alert_type='target_not_achieved', operator='lt',
                           threshold=95.0, threshold_uom='percent')
        self._entry(self.wc_saw, 100.0, 90.0)
        machines = dict(self.engine._eval_target_not_achieved(rule))
        self.assertIn(self.wc_saw, machines)
        self.assertAlmostEqual(machines[self.wc_saw], 90.0, places=4)

    def test_at_threshold_does_not_trigger(self):
        rule = self._rule(alert_type='target_not_achieved', operator='lt',
                           threshold=95.0, threshold_uom='percent')
        self._entry(self.wc_saw, 100.0, 95.0)
        machines = dict(self.engine._eval_target_not_achieved(rule))
        self.assertNotIn(self.wc_saw, machines)

    def test_worst_entry_wins_when_a_machine_has_several(self):
        rule = self._rule(alert_type='target_not_achieved', operator='lt',
                           threshold=95.0, threshold_uom='percent')
        self._entry(self.wc_saw, 100.0, 90.0, shift_id=self.shift_a.id)
        self._entry(self.wc_saw, 100.0, 60.0, shift_id=self.shift_b.id)
        machines = dict(self.engine._eval_target_not_achieved(rule))
        self.assertAlmostEqual(machines[self.wc_saw], 60.0, places=4)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase11')
class TestMaintenanceDue(AlertCase):
    """`lte` operator, both the "due soon" and "overdue" seeded shapes."""

    def _schedule_due_in(self, days):
        # interval_number is always 1: the compute treats interval_number=0
        # as falsy and substitutes 1 (`schedule.interval_number or 1` in
        # fmes_maintenance_schedule.py), so a due-today (days=0) schedule
        # cannot be expressed by varying interval_number itself. Shifting
        # last_done_date instead sidesteps that and works for every value.
        return self.env['fmes.maintenance.schedule'].create({
            'equipment_id': self.equipment_saw.id,
            'trigger_type': 'time_based',
            'interval_number': 1,
            'interval_unit': 'day',
            'lead_time_days': 7,
            'last_done_date': self.today + timedelta(days=days - 1),
        })

    def test_due_soon_boundary(self):
        rule = self._rule(alert_type='maintenance_due', operator='lte',
                           threshold=7, threshold_uom='days')
        due_at_boundary = self._schedule_due_in(7)
        due_past_boundary = self._schedule_due_in(8)
        candidates = dict(self.engine._eval_maintenance_due(rule))
        self.assertIn(due_at_boundary, candidates)
        self.assertEqual(candidates[due_at_boundary], 7)
        self.assertNotIn(due_past_boundary, candidates)

    def test_overdue_boundary(self):
        rule = self._rule(alert_type='maintenance_due', operator='lte',
                           threshold=0, threshold_uom='days')
        due_today = self._schedule_due_in(0)
        due_tomorrow = self._schedule_due_in(1)
        candidates = dict(self.engine._eval_maintenance_due(rule))
        self.assertIn(due_today, candidates)
        self.assertNotIn(due_tomorrow, candidates)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase11')
class TestExcessDowntime(AlertCase):
    """`gt` operator, on real downtime events for the plant's own shifts."""

    def test_hours_boundary(self):
        rule = self._rule(alert_type='excess_downtime', operator='gt',
                           threshold=1.0, threshold_uom='hours')
        self._downtime_event(self.wc_saw, minutes=61)
        machines = dict(self.engine._eval_excess_downtime(rule))
        self.assertIn(self.wc_saw, machines)

    def test_hours_at_threshold_does_not_trigger(self):
        rule = self._rule(alert_type='excess_downtime', operator='gt',
                           threshold=1.0, threshold_uom='hours')
        self._downtime_event(self.wc_saw, minutes=60)
        machines = dict(self.engine._eval_excess_downtime(rule))
        self.assertNotIn(self.wc_saw, machines)

    def test_planned_downtime_is_excluded(self):
        rule = self._rule(alert_type='excess_downtime', operator='gt',
                           threshold=1.0, threshold_uom='hours')
        self._downtime_event(self.wc_saw, minutes=120, loss_ref='mrp.block_reason2')
        machines = dict(self.engine._eval_excess_downtime(rule))
        self.assertNotIn(self.wc_saw, machines)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase11')
class TestScopeFiltering(AlertCase):

    def test_global_scope_matches_any_department_or_machine(self):
        rule = self._rule(scope='global')
        self.assertTrue(rule._department_in_scope(self.dept_cutting))
        self.assertTrue(rule._workcenter_in_scope(self.wc_saw))

    def test_department_scope_restricts_to_selected_departments(self):
        rule = self._rule(scope='department',
                           department_ids=[(6, 0, [self.dept_cutting.id])])
        self.assertTrue(rule._department_in_scope(self.dept_cutting))
        self.assertFalse(rule._department_in_scope(self.dept_finishing))

    def test_workcenter_scope_restricts_to_selected_machines(self):
        rule = self._rule(scope='workcenter',
                           workcenter_ids=[(6, 0, [self.wc_saw.id])])
        self.assertTrue(rule._workcenter_in_scope(self.wc_saw))
        self.assertFalse(rule._workcenter_in_scope(self.wc_spray))

    def test_department_scope_filters_real_evaluation_candidates(self):
        rule = self._rule(
            alert_type='target_not_achieved', operator='lt', threshold=95.0,
            scope='department', department_ids=[(6, 0, [self.dept_cutting.id])])
        self._entry(self.wc_saw, 100.0, 50.0)      # dept_cutting: in scope
        self._entry(self.wc_spray, 100.0, 50.0)    # dept_finishing: out of scope
        machines = dict(self.engine._eval_target_not_achieved(rule))
        self.assertIn(self.wc_saw, machines)
        self.assertNotIn(self.wc_spray, machines)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase11')
class TestRecipientResolution(AlertCase):

    def test_group_and_direct_users_are_unioned_without_duplicates(self):
        # Demo data may add its own members to group_fmes_supervisor, so
        # this does not assert an exact recipient set (that would make the
        # test depend on demo data, which common.py's own fixtures
        # deliberately never do) -- only that both explicit sources are
        # reachable and that the union does not somehow drop or double
        # anyone reachable through both.
        rule = self._rule(
            recipient_group_ids=[(6, 0, [self.group_supervisor.id])],
            # supervisor is already reachable via the group above; the
            # union must not double-count them.
            recipient_user_ids=[(6, 0, [self.manager.id, self.supervisor.id])])
        recipients = rule._resolve_recipients()
        self.assertIn(self.supervisor, recipients)
        self.assertIn(self.manager, recipients)
        self.assertEqual(len(recipients.filtered(lambda u: u == self.supervisor)), 1)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase11')
class TestDeduplicationAndCooldown(AlertCase):

    def test_no_duplicate_while_the_alert_is_still_open(self):
        rule = self._rule(cooldown_minutes=60)
        first = self.engine._raise_alert(rule, self.wc_saw, 42.0)
        self.assertTrue(first)
        second = self.engine._raise_alert(rule, self.wc_saw, 43.0)
        self.assertFalse(second)
        self.assertEqual(
            self.env['fmes.alert'].search_count([('rule_id', '=', rule.id)]), 1)

    def test_reraise_suppressed_within_cooldown_even_once_resolved(self):
        rule = self._rule(cooldown_minutes=60)
        first = self.engine._raise_alert(rule, self.wc_saw, 42.0)
        first.action_resolve()
        second = self.engine._raise_alert(rule, self.wc_saw, 43.0)
        self.assertFalse(second)

    def test_reraise_allowed_once_resolved_and_cooldown_elapsed(self):
        rule = self._rule(cooldown_minutes=60)
        first = self.engine._raise_alert(rule, self.wc_saw, 42.0)
        first.action_resolve()
        first.triggered_on = fields.Datetime.now() - timedelta(minutes=61)
        second = self.engine._raise_alert(rule, self.wc_saw, 43.0)
        self.assertTrue(second)

    def test_different_subjects_do_not_share_a_cooldown(self):
        rule = self._rule(cooldown_minutes=60)
        first = self.engine._raise_alert(rule, self.wc_saw, 42.0)
        second = self.engine._raise_alert(rule, self.wc_spray, 42.0)
        self.assertTrue(first)
        self.assertTrue(second)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase11')
class TestDispatch(AlertCase):

    def test_critical_alert_dispatches_immediately(self):
        rule = self._rule(
            alert_type='machine_breakdown', operator='gt', threshold=0,
            severity='critical', notify_discuss=True,
            recipient_group_ids=[(6, 0, [self.group_supervisor.id])])
        alert = self.engine._raise_alert(rule, self.wc_saw, 1.0)
        self.assertTrue(alert.notified_on)

    def test_warning_alert_is_queued_not_dispatched_immediately(self):
        rule = self._rule(severity='warning')
        alert = self.engine._raise_alert(rule, self.wc_saw, 50.0)
        self.assertFalse(alert.notified_on)

    def test_dispatch_schedules_an_activity_per_recipient(self):
        # Demo data may add its own members to group_fmes_supervisor, so
        # the recipient count is not assumed to be exactly one -- only that
        # every actual recipient (self.supervisor included) got its own
        # activity, matching whatever _resolve_recipients() itself returns.
        rule = self._rule(
            severity='warning', notify_activity=True,
            recipient_group_ids=[(6, 0, [self.group_supervisor.id])])
        alert = self.engine._raise_alert(rule, self.wc_saw, 50.0)
        self.engine._dispatch(alert)
        self.assertTrue(alert.notified_on)
        recipients = rule._resolve_recipients()
        self.assertEqual(len(alert.activity_ids), len(recipients))
        self.assertTrue(alert.activity_ids.filtered(lambda a: a.user_id == self.supervisor))


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase11')
class TestEscalation(AlertCase):

    def _critical_alert(self):
        rule = self._rule(alert_type='machine_breakdown', operator='gt',
                           threshold=0, severity='critical')
        return self.engine._raise_alert(rule, self.wc_saw, 1.0)

    def test_unacknowledged_critical_alert_escalates_after_the_window(self):
        alert = self._critical_alert()
        alert.triggered_on = fields.Datetime.now() - timedelta(minutes=31)
        self.engine._escalate_overdue_critical_alerts()
        self.assertTrue(alert.escalated)
        manager_activities = alert.activity_ids.filtered(
            lambda a: a.user_id == self.manager)
        self.assertTrue(manager_activities)

    def test_not_yet_escalated_before_the_window(self):
        alert = self._critical_alert()
        self.engine._escalate_overdue_critical_alerts()
        self.assertFalse(alert.escalated)

    def test_acknowledged_alert_is_never_escalated(self):
        alert = self._critical_alert()
        alert.triggered_on = fields.Datetime.now() - timedelta(minutes=31)
        alert.action_acknowledge()
        self.engine._escalate_overdue_critical_alerts()
        self.assertFalse(alert.escalated)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase11')
class TestEventTriggers(AlertCase):
    """The base.automation wiring in data/alert_automations.xml.

    Each of these writes the exact field a plant user would, and lets
    base_automation itself decide to call `fmes.alert.engine._on_event` --
    nothing here calls the engine directly, so a broken filter_domain or a
    wrong model_id in the XML would fail these tests.
    """

    def test_breakdown_event_raises_an_alert(self):
        rule = self.env.ref('furnishing_mes.alert_rule_machine_breakdown')
        request = self.env['maintenance.request'].create({
            'name': 'Test breakdown',
            'equipment_id': self.equipment_saw.id,
            'maintenance_type': 'corrective',
        })
        start = fields.Datetime.now() - timedelta(hours=1)
        event = self.env['mrp.workcenter.productivity'].create({
            'workcenter_id': self.wc_saw.id,
            'loss_id': self.env.ref('mrp.block_reason1').id,
            'date_start': start,
            'date_end': start + timedelta(hours=1),
            'fmes_maintenance_request_id': request.id,
        })
        alert = self.env['fmes.alert'].search([
            ('rule_id', '=', rule.id), ('res_model', '=', 'mrp.workcenter.productivity'),
            ('res_id', '=', event.id)])
        self.assertTrue(alert)

    def test_material_shortage_event_raises_an_alert(self):
        rule = self.env.ref('furnishing_mes.alert_rule_material_shortage')
        start = fields.Datetime.now() - timedelta(minutes=30)
        event = self.env['mrp.workcenter.productivity'].create({
            'workcenter_id': self.wc_saw.id,
            'loss_id': self.env.ref('mrp.block_reason0').id,
            'date_start': start,
            'date_end': start + timedelta(minutes=30),
        })
        alert = self.env['fmes.alert'].search([
            ('rule_id', '=', rule.id), ('res_model', '=', 'mrp.workcenter.productivity'),
            ('res_id', '=', event.id)])
        self.assertTrue(alert)

    def test_blocked_order_event_raises_an_alert(self):
        rule = self.env.ref('furnishing_mes.alert_rule_critical_backlog')
        mo = self.env['mrp.production'].create({
            'product_id': self.product_wardrobe.id,
            'product_qty': 10.0,
        })
        mo.write({'fmes_block_reason': 'material'})
        alert = self.env['fmes.alert'].search([
            ('rule_id', '=', rule.id), ('res_model', '=', 'mrp.production'),
            ('res_id', '=', mo.id)])
        self.assertTrue(alert)
