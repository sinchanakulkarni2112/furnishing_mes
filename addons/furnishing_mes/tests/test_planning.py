# -*- coding: utf-8 -*-
"""Phase 3 tests: the planning engine, plan workflow and scheduling board.

The invariant that matters most is capacity: no machine-shift slot may ever be
planned beyond the hours it actually has. A scheduler that quietly overloads a
machine produces a plan the plant cannot meet, which is precisely the failure
mode the customer is trying to escape.
"""

from datetime import date, timedelta

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import HttpCase
from odoo.tools import mute_logger

from .common import FmesTestCase


class PlanningCase(FmesTestCase):
    """Fixture plant plus a small, fully-rated demand set."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plan_from = date(2026, 1, 5)
        cls.plan_to = date(2026, 1, 7)

        # Give every fixture machine a rate for the wardrobe product so the
        # allocator has real choices to make.
        Capacity = cls.env['fmes.capacity.matrix']
        cls.cap_edge = Capacity.create({
            'workcenter_id': cls.wc_edge.id,
            'product_id': cls.product_wardrobe.id,
            'std_output_qty': 5.0,
            'time_basis': 'per_hour',
            'basis_hours': 1.0,
            'std_manpower': 1.0,
            'changeover_minutes': 30,
            'priority': 20,
        })

        cls.mo = cls._make_mo(cls.product_wardrobe, 100.0, date(2026, 1, 9))

    @classmethod
    def _make_mo(cls, product, qty, deadline):
        return cls.env['mrp.production'].create({
            'product_id': product.id,
            'product_qty': qty,
            'date_deadline': deadline,
            'date_start': deadline,
        })

    def _generate(self, **kwargs):
        params = dict(date_from=self.plan_from, date_to=self.plan_to)
        params.update(kwargs)
        return self.env['fmes.planning.engine'].generate(**params)

    def _slot_load(self, plan):
        """Planned hours per (date, shift, machine)."""
        loads = {}
        for line in plan.line_ids:
            key = (line.date, line.shift_id.id, line.workcenter_id.id)
            loads[key] = loads.get(key, 0.0) + line.planned_hours
        return loads


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase3')
class TestCapacityComputation(PlanningCase):

    def test_slot_capacity_is_net_shift_hours(self):
        """A 7.5 hour shift on a 100%-efficient machine gives 7.5 hours."""
        self.wc_saw.time_efficiency = 100.0
        capacity = self.env['fmes.planning.engine']._slot_capacity_hours(
            self.wc_saw, self.shift_a, self.plan_from)
        self.assertAlmostEqual(capacity, 7.5, places=4)

    def test_machine_efficiency_derates_capacity(self):
        self.wc_saw.time_efficiency = 80.0
        capacity = self.env['fmes.planning.engine']._slot_capacity_hours(
            self.wc_saw, self.shift_a, self.plan_from)
        self.assertAlmostEqual(capacity, 6.0, places=4)

    def test_availability_is_full_without_downtime_history(self):
        factor = self.env['fmes.planning.engine']._get_availability_factor(
            self.wc_saw, self.plan_from)
        self.assertEqual(factor, 1.0)

    def test_manpower_factor_is_neutral_until_phase_8(self):
        """Documented behaviour: the roster arrives with operator allocation."""
        factor = self.env['fmes.planning.engine']._get_manpower_factor(
            self.wc_saw, self.shift_a, self.plan_from)
        self.assertEqual(factor, 1.0)

    def test_slots_cover_every_machine_shift_day(self):
        slots = self.env['fmes.planning.engine']._build_capacity_slots(
            self.plan_from, self.plan_to)
        days = (self.plan_to - self.plan_from).days + 1
        # Every fixture machine and shift should appear on every day.
        for machine in (self.wc_saw, self.wc_edge, self.wc_spray):
            for shift in self.shifts:
                for offset in range(days):
                    key = (self.plan_from + timedelta(days=offset),
                           shift.id, machine.id)
                    self.assertIn(key, slots)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase3')
class TestPlanGeneration(PlanningCase):

    def test_generation_produces_a_plan_with_lines(self):
        plan = self._generate()
        self.assertTrue(plan.line_ids)
        self.assertEqual(plan.generated_by, 'auto')
        self.assertEqual(plan.state, 'draft')
        self.assertTrue(plan.name.startswith('PLAN/'))

    def test_no_slot_is_planned_beyond_its_capacity(self):
        """The core invariant of the whole engine."""
        plan = self._generate()
        engine = self.env['fmes.planning.engine']
        for (day, shift_id, machine_id), hours in self._slot_load(plan).items():
            capacity = engine._slot_capacity_hours(
                self.env['mrp.workcenter'].browse(machine_id),
                self.env['fmes.shift'].browse(shift_id), day)
            self.assertLessEqual(
                hours, capacity + 1e-6,
                "Slot %s/%s/%s planned to %.4f h against %.4f h of capacity"
                % (day, shift_id, machine_id, hours, capacity))

    def test_planned_quantity_never_exceeds_demand(self):
        plan = self._generate()
        planned = sum(plan.line_ids.filtered(
            lambda l: l.production_id == self.mo).mapped('planned_qty'))
        self.assertLessEqual(planned, self.mo.product_qty + 1e-6)

    def test_hours_follow_quantity_and_rate(self):
        plan = self._generate()
        for line in plan.line_ids:
            if not line.output_rate:
                continue
            expected = (line.planned_qty / line.output_rate
                        + (line.changeover_minutes or 0) / 60.0)
            self.assertAlmostEqual(line.planned_hours, expected, places=6)

    def test_generation_is_deterministic(self):
        """Same inputs, same plan. Planners distrust a scheduler that drifts."""
        first = self._generate()
        second = self._generate()

        def signature(plan):
            return sorted(
                (str(l.date), l.shift_id.id, l.workcenter_id.id,
                 l.product_id.id, round(l.planned_qty, 6))
                for l in plan.line_ids)

        self.assertEqual(signature(first), signature(second))

    def test_unplaceable_demand_is_reported_not_dropped(self):
        self._make_mo(self.product_unrated, 20.0, date(2026, 1, 9))
        plan = self._generate()
        self.assertTrue(plan.unscheduled_demand_note)
        self.assertIn(self.product_unrated.display_name,
                      plan.unscheduled_demand_note)

    def test_demand_beyond_the_horizon_is_reported(self):
        """A quantity larger than the horizon can hold must be flagged."""
        self._make_mo(self.product_wardrobe, 100000.0, date(2026, 1, 9))
        plan = self._generate()
        self.assertTrue(plan.unscheduled_demand_note)

    def test_changeover_is_charged_when_the_product_changes(self):
        other = self.env['product.product'].create({
            'name': 'Test Second Item',
            'categ_id': self.categ_furniture.id,
        })
        self._make_mo(other, 20.0, date(2026, 1, 6))
        plan = self._generate()
        charged = plan.line_ids.filtered(lambda l: l.changeover_minutes > 0)
        self.assertTrue(
            charged,
            "Switching products on a machine must cost changeover time")

    def test_department_scope_limits_the_machines_used(self):
        plan = self._generate(departments=self.dept_finishing)
        outside = plan.line_ids.filtered(
            lambda l: l.workcenter_id.department_id != self.dept_finishing)
        self.assertFalse(
            outside, "A department-scoped plan must not use other departments")

    def test_totals_match_the_lines(self):
        plan = self._generate()
        self.assertAlmostEqual(
            plan.total_planned_qty,
            sum(plan.line_ids.mapped('planned_qty')), places=4)
        self.assertAlmostEqual(
            plan.total_planned_hours,
            sum(plan.line_ids.mapped('planned_hours')), places=4)
        self.assertEqual(plan.overloaded_line_count, 0)

    def test_preview_agrees_with_what_is_generated(self):
        preview = self.env['fmes.planning.engine'].preview(
            self.plan_from, self.plan_to)
        plan = self._generate()
        self.assertGreater(preview['demand_count'], 0)
        self.assertGreater(preview['available_hours'], 0)
        # The preview sizes demand on the fastest eligible machine, so it is a
        # lower bound on what the plan actually consumes.
        self.assertLessEqual(
            preview['required_hours'], plan.total_planned_hours + 1e-6)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase3')
class TestCarryForward(PlanningCase):

    def _released_plan_with_shortfall(self):
        plan = self._generate()
        plan.action_confirm()
        plan.action_release()
        line = plan.line_ids[0]
        line.write({'qty_done': line.planned_qty / 4.0, 'state': 'partial'})
        return plan, line

    def test_remaining_quantity_is_what_is_left(self):
        plan, line = self._released_plan_with_shortfall()
        self.assertAlmostEqual(
            line.remaining_qty, line.planned_qty - line.qty_done, places=6)

    def test_shortfall_is_carried_into_the_next_plan(self):
        plan, line = self._released_plan_with_shortfall()
        follow_on = self.env['fmes.planning.engine'].generate(
            self.plan_to + timedelta(days=1),
            self.plan_to + timedelta(days=3))
        carried = follow_on.line_ids.filtered(
            lambda l: l.source == 'carry_forward')
        self.assertTrue(
            carried, "Unfinished work must reappear in the next plan")

    def test_carry_forward_conserves_quantity(self):
        """Nothing is lost and nothing is duplicated in the roll-over.

        Every unfinished line of a released plan carries forward, not just the
        partially-produced one — pending work is unfinished work.
        """
        plan, line = self._released_plan_with_shortfall()
        outstanding = sum(plan.line_ids.filtered(
            lambda l: l.state in ('pending', 'in_progress', 'partial')
        ).mapped('remaining_qty'))

        follow_on = self.env['fmes.planning.engine'].generate(
            self.plan_to + timedelta(days=1),
            self.plan_to + timedelta(days=3))
        carried = sum(follow_on.line_ids.filtered(
            lambda l: l.source == 'carry_forward').mapped('planned_qty'))

        self.assertGreater(outstanding, 0)
        self.assertAlmostEqual(carried, outstanding, places=2)

    def test_carry_forward_can_be_switched_off(self):
        plan, line = self._released_plan_with_shortfall()
        follow_on = self.env['fmes.planning.engine'].generate(
            self.plan_to + timedelta(days=1),
            self.plan_to + timedelta(days=3),
            include_carry_forward=False)
        self.assertFalse(
            follow_on.line_ids.filtered(lambda l: l.source == 'carry_forward'))

    def test_carry_forward_records_its_origin(self):
        plan, line = self._released_plan_with_shortfall()
        follow_on = self.env['fmes.planning.engine'].generate(
            self.plan_to + timedelta(days=1),
            self.plan_to + timedelta(days=3))
        carried = follow_on.line_ids.filtered(
            lambda l: l.source == 'carry_forward')
        self.assertTrue(all(c.carry_forward_from_id for c in carried),
                        "Every carried line must point at where it came from")


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase3')
class TestPlanWorkflow(PlanningCase):

    def test_confirm_then_release(self):
        plan = self._generate()
        plan.action_confirm()
        self.assertEqual(plan.state, 'confirmed')
        plan.action_release()
        self.assertEqual(plan.state, 'released')

    def test_release_requires_confirmation(self):
        plan = self._generate()
        with self.assertRaises(UserError):
            plan.action_release()

    def test_empty_plan_cannot_be_confirmed(self):
        plan = self.env['fmes.production.plan'].create({
            'date_from': self.plan_from, 'date_to': self.plan_to})
        with self.assertRaises(UserError):
            plan.action_confirm()

    def test_release_pushes_dates_onto_the_manufacturing_order(self):
        plan = self._generate()
        plan.action_confirm()
        plan.action_release()
        lines = plan.line_ids.filtered(lambda l: l.production_id == self.mo)
        self.assertTrue(lines)
        earliest = min(line._slot_datetimes()[0] for line in lines)
        self.assertEqual(self.mo.date_start, earliest)

    def test_cancel_cancels_the_lines(self):
        plan = self._generate()
        plan.action_cancel()
        self.assertEqual(plan.state, 'cancelled')
        self.assertTrue(all(l.state == 'cancelled' for l in plan.line_ids))

    def test_plan_dates_must_be_ordered(self):
        with self.assertRaises(ValidationError):
            self.env['fmes.production.plan'].create({
                'date_from': self.plan_to, 'date_to': self.plan_from})

    @mute_logger('odoo.sql_db')
    def test_line_quantity_must_be_positive(self):
        plan = self._generate()
        with self.assertRaises(IntegrityError):
            self.env['fmes.production.plan.line'].create({
                'plan_id': plan.id,
                'date': self.plan_from,
                'shift_id': self.shift_a.id,
                'workcenter_id': self.wc_saw.id,
                'product_id': self.product_wardrobe.id,
                'planned_qty': 0.0,
            })
            self.env.flush_all()


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase3')
class TestShiftSlotTimes(PlanningCase):

    def test_night_shift_slot_ends_on_the_next_day(self):
        start, end = self.shift_c._slot_datetimes(self.plan_from)
        self.assertGreater(end, start)
        self.assertAlmostEqual(
            (end - start).total_seconds() / 3600.0, 8.0, places=4)

    def test_day_shift_slot_spans_the_shift(self):
        start, end = self.shift_a._slot_datetimes(self.plan_from)
        self.assertAlmostEqual(
            (end - start).total_seconds() / 3600.0, 8.0, places=4)

    def test_slot_uses_the_company_timezone_not_the_users(self):
        """A shift belongs to the plant, not to whoever opens the screen."""
        self.env.company.partner_id.tz = 'Asia/Kolkata'
        start_company, _end = self.shift_a._slot_datetimes(self.plan_from)

        other_user = self._create_user(
            'fmes_tz_user', 'furnishing_mes.group_fmes_manager')
        other_user.tz = 'America/New_York'
        start_other, _e = self.shift_a.with_user(
            other_user)._slot_datetimes(self.plan_from)

        self.assertEqual(
            start_company, start_other,
            "The same shift must resolve to the same instant for every user")


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase3')
class TestSchedulingBoard(PlanningCase):

    def test_board_data_has_axes_and_cells(self):
        plan = self._generate()
        data = self.env['fmes.production.plan'].get_board_data(
            self.plan_from, self.plan_to, plan_id=plan.id)
        self.assertEqual(len(data['dates']), 3)
        self.assertTrue(data['shifts'])
        self.assertTrue(data['machines'])
        self.assertTrue(data['cells'])
        self.assertEqual(data['plan']['id'], plan.id)

    def test_board_percentages_are_computed_on_the_server(self):
        plan = self._generate()
        data = self.env['fmes.production.plan'].get_board_data(
            self.plan_from, self.plan_to, plan_id=plan.id)
        for cell in data['cells'].values():
            if cell.get('capacity'):
                self.assertAlmostEqual(
                    cell['pct'], cell['hours'] / cell['capacity'] * 100.0,
                    places=4)

    def test_board_never_reports_an_overloaded_cell_for_a_generated_plan(self):
        plan = self._generate()
        data = self.env['fmes.production.plan'].get_board_data(
            self.plan_from, self.plan_to, plan_id=plan.id)
        # A hair of floating-point tolerance: 100.0000001% is not an overload.
        over = [k for k, c in data['cells'].items()
                if (c.get('pct') or 0) > 100.01]
        self.assertFalse(over, "Generated plans must never overload a slot")

    def test_move_relocates_lines_and_resizes_them(self):
        plan = self._generate()
        # A small line, so the move is about relocation rather than capacity.
        line = self.env['fmes.production.plan.line'].create({
            'plan_id': plan.id,
            'date': self.plan_from,
            'shift_id': self.shift_a.id,
            'workcenter_id': self.wc_saw.id,
            'product_id': self.product_wardrobe.id,
            'planned_qty': 10.0,
            'planned_hours': 1.0,
            'output_rate': 10.0,
        })
        result = self.env['fmes.production.plan'].move_plan_lines(
            line.ids, self.wc_edge.id, str(self.plan_to), self.shift_b.id)
        self.assertTrue(result['ok'], result.get('error'))
        self.assertEqual(line.workcenter_id, self.wc_edge)
        self.assertEqual(line.shift_id, self.shift_b)
        self.assertEqual(line.date, self.plan_to)
        # The edge bander is slower, so the same quantity now takes longer.
        self.assertAlmostEqual(
            line.output_rate, self.cap_edge.effective_output_per_hour, places=4)
        # Edge bander: 5/hour plus its own 30-minute changeover.
        self.assertAlmostEqual(line.planned_hours, 10.0 / 5.0 + 0.5, places=4)
        self.assertEqual(line.changeover_minutes, 30)

    def test_move_is_refused_when_the_target_has_no_rate(self):
        plan = self._generate()
        line = plan.line_ids[:1]
        result = self.env['fmes.production.plan'].move_plan_lines(
            line.ids, self.wc_spray.id, str(self.plan_from), self.shift_a.id)
        self.assertFalse(result['ok'])
        self.assertIn('capacity rate', result['error'])

    def test_move_is_refused_when_it_would_overload_the_target(self):
        plan = self._generate()
        big = self.env['fmes.production.plan.line'].create({
            'plan_id': plan.id,
            'date': self.plan_from,
            'shift_id': self.shift_a.id,
            'workcenter_id': self.wc_saw.id,
            'product_id': self.product_wardrobe.id,
            'planned_qty': 100000.0,
            'planned_hours': 10000.0,
            'output_rate': 10.0,
        })
        result = self.env['fmes.production.plan'].move_plan_lines(
            big.ids, self.wc_edge.id, str(self.plan_from), self.shift_a.id)
        self.assertFalse(result['ok'])
        self.assertIn('overloaded', result['error'])


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase3')
class TestPlanGeneratorWizard(PlanningCase):

    def test_preview_fields_are_populated(self):
        wizard = self.env['fmes.plan.generator'].create({
            'date_from': self.plan_from, 'date_to': self.plan_to})
        self.assertGreater(wizard.machine_shift_slots, 0)
        self.assertGreater(wizard.available_hours, 0.0)
        self.assertGreaterEqual(wizard.demand_count, 1)

    def test_wizard_generates_a_plan(self):
        wizard = self.env['fmes.plan.generator'].create({
            'date_from': self.plan_from, 'date_to': self.plan_to})
        action = wizard.action_generate()
        plan = self.env['fmes.production.plan'].browse(action['res_id'])
        self.assertTrue(plan.line_ids)
        self.assertEqual(plan.generated_by, 'auto')

    def test_reversed_dates_are_rejected(self):
        wizard = self.env['fmes.plan.generator'].create({
            'date_from': self.plan_to, 'date_to': self.plan_from})
        with self.assertRaises(UserError):
            wizard.action_generate()

    def test_warning_when_products_have_no_rate(self):
        self._make_mo(self.product_unrated, 10.0, date(2026, 1, 9))
        wizard = self.env['fmes.plan.generator'].create({
            'date_from': self.plan_from, 'date_to': self.plan_to})
        self.assertGreaterEqual(wizard.unrated_count, 1)
        self.assertTrue(wizard.preview_warning)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase3')
class TestPlanningAccess(PlanningCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = cls._create_user(
            'fmes_operator_p3', 'furnishing_mes.group_fmes_operator')
        cls.supervisor = cls._create_user(
            'fmes_supervisor_p3', 'furnishing_mes.group_fmes_supervisor')

    def test_operator_may_read_but_not_write_plans(self):
        plan = self._generate()
        self.assertTrue(plan.with_user(self.operator).name)
        with self.assertRaises(AccessError):
            plan.with_user(self.operator).write({'note': 'nope'})

    def test_operator_cannot_create_plan_lines(self):
        plan = self._generate()
        with self.assertRaises(AccessError):
            self.env['fmes.production.plan.line'].with_user(
                self.operator).create({
                    'plan_id': plan.id,
                    'date': self.plan_from,
                    'shift_id': self.shift_a.id,
                    'workcenter_id': self.wc_saw.id,
                    'product_id': self.product_wardrobe.id,
                    'planned_qty': 5.0,
                })

    def test_supervisor_may_plan(self):
        plan = self._generate()
        plan.with_user(self.supervisor).write({'note': 'reviewed'})
        self.assertEqual(plan.note, 'reviewed')

    def test_operator_cannot_move_plan_lines(self):
        plan = self._generate()
        line = plan.line_ids[:1]
        with self.assertRaises(AccessError):
            self.env['fmes.production.plan'].with_user(
                self.operator).move_plan_lines(
                    line.ids, self.wc_edge.id, str(self.plan_from),
                    self.shift_b.id)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase3')
class TestPlanXlsxExport(HttpCase):
    """The Excel export route.

    Planners will keep sharing schedules as spreadsheets for a while after
    go-live, so this is the bridge that makes leaving manual planning painless.
    """

    def test_export_returns_a_workbook(self):
        plan = self.env['fmes.production.plan'].create({
            'date_from': date(2026, 1, 5),
            'date_to': date(2026, 1, 7),
        })
        self.authenticate('admin', 'admin')
        response = self.url_open('/fmes/plan/%s/xlsx' % plan.id, timeout=60)
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response.headers.get('Content-Type', ''))
        # A real XLSX is a ZIP container: check the magic bytes rather than
        # trusting the content type alone.
        self.assertTrue(response.content.startswith(b'PK'))
        self.assertGreater(len(response.content), 2000)

    def test_export_of_a_missing_plan_is_not_found(self):
        self.authenticate('admin', 'admin')
        response = self.url_open('/fmes/plan/999999/xlsx', timeout=60)
        self.assertEqual(response.status_code, 404)
