# -*- coding: utf-8 -*-
"""The production planning engine.

Requirement 1: generate production plans automatically from the machine
capacity matrix, allowing for shift hours, machine availability and manpower,
producing machine-wise and shift-wise schedules.

Design notes
------------
The engine is an ``AbstractModel`` with no state of its own, so it can be driven
identically by the wizard, by a cron, or by a test. Everything it needs comes in
as arguments and everything it decides comes out as plan lines.

It is **deterministic**: the same demand and the same masters always produce the
same plan. Planners lose trust in a scheduler whose output moves for no visible
reason, so ordering is fully specified at every step and never depends on
database ids.

It is also **explainable**: every line records the rate it was sized with, and
demand the engine could not place is reported back with the reason rather than
being dropped silently.
"""

from collections import defaultdict, OrderedDict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.tools import float_round

# How far back to look when derating a machine for its unplanned downtime.
AVAILABILITY_LOOKBACK_DAYS = 90
# Never derate a machine below this, however bad its history: a machine that
# broke down constantly last quarter is a maintenance problem, and planning it
# at near-zero capacity would just push the plan somewhere equally unrealistic.
MIN_AVAILABILITY_FACTOR = 0.5


class FmesPlanningEngine(models.AbstractModel):
    _name = 'fmes.planning.engine'
    _description = 'Production Planning Engine'

    # ==================================================================
    # Public API
    # ==================================================================
    @api.model
    def generate(self, date_from, date_to, plan_type='weekly',
                 departments=None, demand_source='open_mo',
                 include_carry_forward=True, company=None):
        """Build a production plan for a date range.

        :param date_from: first day covered, inclusive
        :param date_to: last day covered, inclusive
        :param plan_type: ``daily`` / ``weekly`` / ``monthly``
        :param departments: ``hr.department`` recordset, or None for all
        :param demand_source: ``open_mo`` or ``mo_and_so``
        :param include_carry_forward: pull unfinished work from earlier plans
        :param company: ``res.company``, defaults to the active company
        :return: the created ``fmes.production.plan``
        """
        company = company or self.env.company
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)

        plan = self.env['fmes.production.plan'].create({
            'plan_type': plan_type,
            'date_from': date_from,
            'date_to': date_to,
            'department_ids': [(6, 0, departments.ids)] if departments else False,
            'generated_by': 'auto',
            'company_id': company.id,
        })

        demands = self._collect_demand(
            date_from, date_to, departments=departments,
            demand_source=demand_source,
            include_carry_forward=include_carry_forward, company=company)

        slots = self._build_capacity_slots(
            date_from, date_to, departments=departments, company=company)

        lines, unplaced = self._allocate(demands, slots, plan)

        if lines:
            self.env['fmes.production.plan.line'].create(lines)
        plan.unscheduled_demand_note = self._format_unplaced(unplaced)
        return plan

    # ==================================================================
    # Step 1 — demand
    # ==================================================================
    @api.model
    def _collect_demand(self, date_from, date_to, departments=None,
                        demand_source='open_mo', include_carry_forward=True,
                        company=None):
        """Gather what has to be produced, most urgent first.

        Each demand is a plain dict so the allocator never has to care whether
        it came from a work order, a manufacturing order or a carry-forward.
        """
        company = company or self.env.company
        demands = []

        if include_carry_forward:
            demands += self._collect_carry_forward(date_from, company)

        productions = self.env['mrp.production'].search([
            ('company_id', '=', company.id),
            ('state', 'in', ('draft', 'confirmed', 'progress')),
        ])
        for production in productions:
            demands += self._demands_for_production(production, departments)

        if demand_source == 'mo_and_so':
            demands += self._collect_sale_order_demand(
                date_to, departments, company, productions)

        # Carry-forward first, then urgent, then earliest deadline. Ties break
        # on the order reference so the result never depends on database ids.
        def sort_key(demand):
            return (
                0 if demand['source'] == 'carry_forward' else 1,
                0 if demand['priority'] == '1' else 1,
                demand['deadline'] or fields.Date.to_date('2099-12-31'),
                demand['origin'],
                demand['sequence'],
            )

        return sorted(demands, key=sort_key)

    @api.model
    def _demands_for_production(self, production, departments=None):
        """One demand per routing operation, or one for the order itself.

        When the bill of materials defines operations, each work order is
        planned on its own machine — which is what a machine-wise schedule
        means. Without operations there is nothing to say which machine should
        run the order, so the engine picks from the capacity matrix.
        """
        remaining = production.product_qty - production.qty_produced
        if remaining <= 0:
            return []

        base = {
            'product': production.product_id,
            'qty': remaining,
            'deadline': fields.Date.to_date(production.date_deadline)
            if production.date_deadline else None,
            'priority': production.priority or '0',
            'production': production,
            'origin': production.name or '',
            'source': 'auto',
        }

        workorders = production.workorder_ids.filtered(
            lambda w: w.state not in ('done', 'cancel'))
        if not workorders:
            if departments:
                # Without a routing there is no department to filter on; the
                # allocator will choose a machine and may land outside scope,
                # so such orders are only planned when planning everything.
                return []
            demand = dict(base, workorder=None, workcenter=None, sequence=0)
            return [demand]

        demands = []
        for index, workorder in enumerate(workorders.sorted(
                lambda w: (w.operation_id.sequence or 0, w.id))):
            workcenter = workorder.workcenter_id
            if departments and workcenter.department_id not in departments:
                continue
            demands.append(dict(
                base, workorder=workorder, workcenter=workcenter,
                sequence=index))
        return demands

    @api.model
    def _collect_carry_forward(self, date_from, company):
        """Unfinished work from released plans that end before this one starts.

        Requirement 4.3. Anything still outstanding must be planned again
        before new orders, or it silently disappears from the schedule.
        """
        lines = self.env['fmes.production.plan.line'].search([
            ('company_id', '=', company.id),
            ('date', '<', date_from),
            ('state', 'in', ('pending', 'in_progress', 'partial')),
            ('plan_id.state', 'in', ('released', 'in_progress')),
        ])
        demands = []
        for line in lines:
            if line.remaining_qty <= 0:
                continue
            demands.append({
                'product': line.product_id,
                'qty': line.remaining_qty,
                'deadline': line.date_deadline or line.date,
                'priority': line.priority,
                'production': line.production_id,
                'workorder': line.workorder_id,
                'workcenter': line.workcenter_id,
                'origin': line.plan_id.name or '',
                'sequence': 0,
                'source': 'carry_forward',
                'carry_forward_from': line,
            })
        return demands

    @api.model
    def _collect_sale_order_demand(self, date_to, departments, company,
                                   known_productions):
        """Confirmed sale order lines with no manufacturing order yet.

        Lets a planner see committed demand before the orders are released to
        production. Skipped by default.
        """
        if departments:
            return []
        covered = known_productions.mapped('product_id')
        order_lines = self.env['sale.order.line'].search([
            ('order_id.state', '=', 'sale'),
            ('order_id.company_id', '=', company.id),
            ('product_id.type', '!=', 'service'),
        ])
        demands = []
        for index, line in enumerate(order_lines):
            if line.product_id in covered:
                continue
            qty = line.product_uom_qty - line.qty_delivered
            if qty <= 0:
                continue
            demands.append({
                'product': line.product_id,
                'qty': qty,
                'deadline': fields.Date.to_date(line.order_id.commitment_date)
                if line.order_id.commitment_date else date_to,
                'priority': '0',
                'production': self.env['mrp.production'],
                'workorder': None,
                'workcenter': None,
                'origin': line.order_id.name or '',
                'sequence': index,
                'source': 'auto',
            })
        return demands

    # ==================================================================
    # Step 2 — capacity
    # ==================================================================
    @api.model
    def _build_capacity_slots(self, date_from, date_to, departments=None,
                              company=None):
        """Remaining hours for every machine-shift-day in the range.

        Returned as an ordered mapping so the allocator walks time forwards and
        the outcome is reproducible.
        """
        company = company or self.env.company
        machine_domain = [('company_id', 'in', (company.id, False)),
                          ('active', '=', True)]
        if departments:
            machine_domain.append(('department_id', 'in', departments.ids))
        machines = self.env['mrp.workcenter'].search(
            machine_domain, order='fmes_is_bottleneck desc, id')
        shifts = self.env['fmes.shift'].search(
            [('company_id', '=', company.id)], order='sequence, start_time, id')

        slots = OrderedDict()
        day = date_from
        while day <= date_to:
            for shift in shifts:
                for machine in machines:
                    capacity = self._slot_capacity_hours(machine, shift, day)
                    if capacity > 0:
                        slots[(day, shift.id, machine.id)] = {
                            'capacity': capacity,
                            'remaining': capacity,
                            'last_product': None,
                        }
            day += timedelta(days=1)
        return slots

    @api.model
    def _slot_capacity_hours(self, machine, shift, day):
        """Hours a machine can actually work in one shift.

        net shift hours
          x machine time efficiency
          x availability (its recent unplanned downtime record)
          x manpower factor
        """
        if not machine or not shift:
            return 0.0
        hours = shift.net_hours or 0.0
        hours *= (machine.time_efficiency or 100.0) / 100.0
        hours *= self._get_availability_factor(machine, day)
        hours *= self._get_manpower_factor(machine, shift, day)
        return max(hours, 0.0)

    @api.model
    def _get_availability_factor(self, machine, day):
        """Derate a machine by its recent unplanned downtime.

        Planning every machine at 100% availability is the most common reason a
        plan cannot be met, so the engine uses what actually happened. Planned
        stoppages are excluded — they are already known and scheduled.

        Returns 1.0 when there is no history, which is the case until downtime
        capture goes live in Phase 5.
        """
        productivity = self.env['mrp.workcenter.productivity']
        since = fields.Datetime.to_datetime(day) - timedelta(
            days=AVAILABILITY_LOOKBACK_DAYS)
        logs = productivity.search([
            ('workcenter_id', '=', machine.id),
            ('date_start', '>=', since),
            ('loss_id.fmes_is_planned', '=', False),
            ('loss_id.loss_type', '!=', 'productive'),
        ])
        if not logs:
            return 1.0

        lost_hours = sum(logs.mapped('duration')) / 60.0
        # Available hours over the window, from the machine's own calendar.
        calendar_hours = AVAILABILITY_LOOKBACK_DAYS * 24.0
        if machine.resource_calendar_id:
            attendance = sum(
                machine.resource_calendar_id.attendance_ids.mapped(
                    'duration_hours') or [0.0])
            if attendance:
                calendar_hours = attendance * (AVAILABILITY_LOOKBACK_DAYS / 7.0)
        if calendar_hours <= 0:
            return 1.0
        factor = 1.0 - (lost_hours / calendar_hours)
        return max(min(factor, 1.0), MIN_AVAILABILITY_FACTOR)

    @api.model
    def _get_manpower_factor(self, machine, shift, day):
        """Scale capacity by the operators actually rostered.

        A machine needing two operators but staffed by one cannot run at full
        rate. The roster itself arrives with operator allocation in Phase 8;
        until then every machine is treated as fully staffed, which is the
        behaviour the plant has today.

        Phase 8 replaces the body of this method and nothing else in the
        engine has to change.
        """
        return 1.0

    # ==================================================================
    # Step 3 — allocation
    # ==================================================================
    @api.model
    def _allocate(self, demands, slots, plan):
        """Place demand into capacity slots, earliest deadline first.

        Greedy forward scheduling: walk each demand through time until its
        quantity is placed or the horizon runs out. Greedy is the right choice
        here — a planner needs to understand why a line landed where it did,
        and an optimiser that shaves an hour at the cost of explainability is a
        poor trade in a plant that is coming off spreadsheets.
        """
        line_vals = []
        unplaced = []
        sequence_by_slot = defaultdict(int)
        precision = self.env['decimal.precision'].precision_get(
            'Product Unit of Measure')

        for demand in demands:
            remaining_qty = demand['qty']
            machines = self._eligible_machines(demand)
            if not machines:
                unplaced.append((demand, _("no machine has a capacity rate "
                                           "for this product")))
                continue

            placed_any = False
            for (day, shift_id, machine_id), slot in slots.items():
                if remaining_qty <= 0:
                    break
                if slot['remaining'] <= 0:
                    continue
                machine = machines.get(machine_id)
                if machine is None:
                    continue

                rate = machine['rate']
                changeover = 0
                if slot['last_product'] not in (None, demand['product'].id):
                    changeover = machine['changeover']
                usable = slot['remaining'] - changeover / 60.0
                if usable <= 0:
                    continue

                # Two properties have to hold together: the hours must never
                # exceed the slot's remaining capacity, and hours must still
                # equal quantity / rate + changeover exactly, so a planner
                # checking the arithmetic by hand finds it adds up.
                capacity_qty = usable * rate
                if remaining_qty <= capacity_qty:
                    # The slot can absorb the rest, so place it exactly.
                    # Rounding down here would leave a crumb of a unit behind
                    # and report it as unscheduled, which reads as a defect.
                    qty_here = float_round(remaining_qty,
                                           precision_digits=precision)
                    if qty_here / rate + changeover / 60.0 > slot['remaining']:
                        qty_here = float_round(remaining_qty,
                                               precision_digits=precision,
                                               rounding_method='DOWN')
                else:
                    # Filling the slot: round down so the hours fit inside it.
                    qty_here = float_round(capacity_qty,
                                           precision_digits=precision,
                                           rounding_method='DOWN')
                if qty_here <= 0:
                    continue
                hours_here = qty_here / rate + changeover / 60.0

                sequence_by_slot[(day, shift_id, machine_id)] += 10
                line_vals.append({
                    'plan_id': plan.id,
                    'date': day,
                    'shift_id': shift_id,
                    'workcenter_id': machine_id,
                    'product_id': demand['product'].id,
                    'production_id': demand['production'].id
                    if demand.get('production') else False,
                    'workorder_id': demand['workorder'].id
                    if demand.get('workorder') else False,
                    'date_deadline': demand['deadline'],
                    'planned_qty': qty_here,
                    'planned_hours': hours_here,
                    'changeover_minutes': changeover,
                    'output_rate': rate,
                    'planned_manpower': machine['manpower'],
                    'priority': demand['priority'],
                    'source': demand['source'],
                    'carry_forward_from_id': demand.get(
                        'carry_forward_from', self.env['fmes.production.plan.line']).id
                    if demand.get('carry_forward_from') else False,
                    'sequence': sequence_by_slot[(day, shift_id, machine_id)],
                })
                slot['remaining'] -= hours_here
                slot['last_product'] = demand['product'].id
                remaining_qty -= qty_here
                placed_any = True

            if remaining_qty > 1e-6:
                reason = (_("only part of the quantity fits in the horizon; "
                            "%(qty).2f left over", qty=remaining_qty)
                          if placed_any else
                          _("no capacity left in the horizon"))
                unplaced.append((demand, reason))

        return line_vals, unplaced

    @api.model
    def _eligible_machines(self, demand):
        """Machines that can make this product, with their rate and setup.

        A routing operation pins the machine. Otherwise every machine with a
        capacity rate is a candidate, preferred by the matrix's own priority.
        """
        capacity_model = self.env['fmes.capacity.matrix']
        product = demand['product']

        if demand.get('workcenter'):
            candidates = demand['workcenter']
        else:
            rows = capacity_model.search([('active', '=', True)])
            candidates = rows.mapped('workcenter_id')

        eligible = {}
        for machine in candidates:
            row = capacity_model._resolve(machine, product)
            if not row or not row.effective_output_per_hour:
                continue
            eligible[machine.id] = {
                'rate': row.effective_output_per_hour,
                'changeover': row.changeover_minutes or 0,
                'manpower': row.std_manpower or machine.fmes_std_manpower,
                'priority': row.priority,
            }
        return eligible

    @api.model
    def _format_unplaced(self, unplaced):
        if not unplaced:
            return False
        lines = [_("The engine could not place the following demand:"), '']
        for demand, reason in unplaced:
            lines.append('- %s / %s (%.2f): %s' % (
                demand['origin'] or _('unknown order'),
                demand['product'].display_name,
                demand['qty'], reason))
        return '\n'.join(lines)

    # ==================================================================
    # Preview — used by the wizard before anything is created
    # ==================================================================
    @api.model
    def preview(self, date_from, date_to, departments=None,
                demand_source='open_mo', include_carry_forward=True,
                company=None):
        """Summarise demand against capacity without creating a plan."""
        company = company or self.env.company
        demands = self._collect_demand(
            date_from, date_to, departments=departments,
            demand_source=demand_source,
            include_carry_forward=include_carry_forward, company=company)
        slots = self._build_capacity_slots(
            date_from, date_to, departments=departments, company=company)

        required_hours = 0.0
        unrated = 0
        for demand in demands:
            machines = self._eligible_machines(demand)
            if not machines:
                unrated += 1
                continue
            best_rate = max(m['rate'] for m in machines.values())
            required_hours += demand['qty'] / best_rate

        available_hours = sum(slot['capacity'] for slot in slots.values())
        return {
            'demand_count': len(demands),
            'carry_forward_count': sum(
                1 for d in demands if d['source'] == 'carry_forward'),
            'unrated_count': unrated,
            'required_hours': required_hours,
            'available_hours': available_hours,
            'utilization_pct': (required_hours / available_hours * 100.0)
            if available_hours else 0.0,
            'machine_shift_slots': len(slots),
        }
