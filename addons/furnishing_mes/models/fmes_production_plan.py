# -*- coding: utf-8 -*-
"""Production plan and plan lines.

Requirement 1: the system generates capacity-aware, machine-wise, shift-wise
production plans instead of the plant maintaining them in Excel.

A plan is a header over a date range; a plan line is one machine, one shift, one
product, one quantity. That grain is what makes the plan directly comparable
with the daily production entries recorded in Phase 4 — planned versus actual
falls out of the same key.
"""

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

PLAN_STATES = [
    ('draft', 'Draft'),
    ('confirmed', 'Confirmed'),
    ('released', 'Released'),
    ('in_progress', 'In Progress'),
    ('done', 'Done'),
    ('cancelled', 'Cancelled'),
]

LINE_STATES = [
    ('pending', 'Pending'),
    ('in_progress', 'In Progress'),
    ('partial', 'Partial'),
    ('done', 'Done'),
    ('cancelled', 'Cancelled'),
]


class FmesProductionPlan(models.Model):
    _name = 'fmes.production.plan'
    _description = 'Production Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'

    name = fields.Char(
        required=True, copy=False, readonly=True, default=lambda self: _('New'))
    plan_type = fields.Selection(
        [('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly')],
        string='Plan Type', required=True, default='weekly', tracking=True)
    date_from = fields.Date(required=True, tracking=True,
                            default=fields.Date.context_today)
    date_to = fields.Date(required=True, tracking=True)
    department_ids = fields.Many2many(
        'hr.department', string='Departments',
        help="Leave empty to plan every department.")

    state = fields.Selection(
        PLAN_STATES, default='draft', required=True, tracking=True,
        help="Draft plans are working copies. Releasing a plan pushes its dates "
             "onto the manufacturing orders and work orders it covers.")
    generated_by = fields.Selection(
        [('auto', 'Planning Engine'), ('manual', 'Manual')],
        default='manual', required=True, readonly=True,
        help="Whether the planning engine produced this plan or a planner "
             "built it by hand.")

    line_ids = fields.One2many(
        'fmes.production.plan.line', 'plan_id', string='Plan Lines',
        copy=True)
    line_count = fields.Integer(compute='_compute_totals', store=True)

    total_planned_qty = fields.Float(
        compute='_compute_totals', store=True,
        digits='Product Unit of Measure', string='Planned Quantity')
    total_planned_hours = fields.Float(
        compute='_compute_totals', store=True, string='Planned Hours')
    total_available_hours = fields.Float(
        compute='_compute_totals', store=True, string='Available Hours',
        help="Capacity of every machine-shift this plan touches.")
    capacity_utilization_pct = fields.Float(
        compute='_compute_totals', store=True, string='Capacity Utilisation %',
        help="Planned hours as a share of available capacity. Above 100% means "
             "the plan cannot be executed as it stands.")
    overloaded_line_count = fields.Integer(
        compute='_compute_totals', store=True, string='Overloaded Slots',
        help="Machine-shift slots whose planned hours exceed their capacity.")

    unscheduled_demand_note = fields.Text(
        string='Unscheduled Demand', readonly=True,
        help="Demand the engine could not place, and why. Recorded so a "
             "planner is never left wondering what happened to an order.")

    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company)
    note = fields.Text(string='Notes')

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('line_ids.planned_qty', 'line_ids.planned_hours',
                 'line_ids.state')
    def _compute_totals(self):
        for plan in self:
            live = plan.line_ids.filtered(lambda l: l.state != 'cancelled')
            plan.line_count = len(live)
            plan.total_planned_qty = sum(live.mapped('planned_qty'))
            plan.total_planned_hours = sum(live.mapped('planned_hours'))

            # Capacity of the distinct machine-shift-date slots in use.
            available = 0.0
            overloaded = 0
            slots = {}
            for line in live:
                key = (line.date, line.shift_id.id, line.workcenter_id.id)
                slots.setdefault(key, []).append(line)
            engine = self.env['fmes.planning.engine']
            for (date, shift_id, wc_id), lines in slots.items():
                capacity = engine._slot_capacity_hours(
                    self.env['mrp.workcenter'].browse(wc_id),
                    self.env['fmes.shift'].browse(shift_id),
                    date)
                available += capacity
                if sum(l.planned_hours for l in lines) > capacity + 1e-6:
                    overloaded += 1
            plan.total_available_hours = available
            plan.overloaded_line_count = overloaded
            plan.capacity_utilization_pct = (
                plan.total_planned_hours / available * 100.0) if available else 0.0

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for plan in self:
            if plan.date_from > plan.date_to:
                raise ValidationError(_(
                    "The plan's start date must not be after its end date."))

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'fmes.production.plan') or _('New')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_confirm(self):
        for plan in self:
            if not plan.line_ids:
                raise UserError(_(
                    "Plan %s has no lines to confirm.", plan.name))
            plan.state = 'confirmed'

    def action_release(self):
        """Release the plan onto the shop floor.

        Pushes the planned dates onto the manufacturing orders and, where the
        bill of materials defines operations, onto their work orders. This is
        what turns a plan into something the shop floor can act on.
        """
        for plan in self:
            if plan.state not in ('confirmed', 'released'):
                raise UserError(_(
                    "Confirm plan %s before releasing it.", plan.name))
            plan._apply_dates_to_manufacturing()
            plan.state = 'released'
            plan.line_ids.filtered(
                lambda l: l.state == 'pending').write({'state': 'pending'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def action_cancel(self):
        for plan in self:
            plan.line_ids.write({'state': 'cancelled'})
            plan.state = 'cancelled'

    def action_done(self):
        self.write({'state': 'done'})

    def _apply_dates_to_manufacturing(self):
        """Align manufacturing and work order dates with the plan.

        A manufacturing order spans every plan line that references it, so its
        start is the earliest planned slot and its finish the latest. Work
        orders are aligned per work center, which is the level the shop floor
        actually works at.
        """
        self.ensure_one()
        by_production = {}
        by_workorder = {}
        for line in self.line_ids.filtered(
                lambda l: l.state != 'cancelled' and l.production_id):
            start, stop = line._slot_datetimes()
            key = line.production_id
            span = by_production.setdefault(key, [start, stop])
            span[0], span[1] = min(span[0], start), max(span[1], stop)
            if line.workorder_id:
                wo_span = by_workorder.setdefault(line.workorder_id, [start, stop])
                wo_span[0] = min(wo_span[0], start)
                wo_span[1] = max(wo_span[1], stop)

        for production, (start, stop) in by_production.items():
            if production.state in ('done', 'cancel'):
                continue
            production.write({'date_start': start, 'date_finished': stop})

        for workorder, (start, stop) in by_workorder.items():
            if workorder.state in ('done', 'cancel'):
                continue
            workorder.write({'date_start': start, 'date_finished': stop})

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_open_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Plan Lines: %s', self.name),
            'res_model': 'fmes.production.plan.line',
            'view_mode': 'list,form',
            'domain': [('plan_id', '=', self.id)],
            'context': {'default_plan_id': self.id},
        }

    def action_open_board(self):
        """Open the scheduling board focused on this plan."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'fmes_scheduling_board',
            'name': _('Scheduling Board: %s', self.name),
            'params': {
                'plan_id': self.id,
                'date_from': str(self.date_from),
                'date_to': str(self.date_to),
            },
        }

    def action_export_xlsx(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/fmes/plan/%s/xlsx' % self.id,
            'target': 'self',
        }


    # ==================================================================
    # Scheduling board API
    # ==================================================================
    @api.model
    def get_board_data(self, date_from, date_to, plan_id=None,
                       department_ids=None):
        """Data behind the scheduling board.

        Machines on one axis, date-shift slots on the other, with the planned
        load and capacity of every cell. Shaped for rendering so the client
        does no arithmetic of its own — the load percentage a planner acts on
        is the same number the server computed.
        """
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        engine = self.env['fmes.planning.engine']

        domain = [('date', '>=', date_from), ('date', '<=', date_to),
                  ('state', '!=', 'cancelled')]
        if plan_id:
            domain.append(('plan_id', '=', plan_id))
        if department_ids:
            domain.append(('department_id', 'in', department_ids))
        lines = self.env['fmes.production.plan.line'].search(domain)

        shifts = self.env['fmes.shift'].search(
            [('company_id', '=', self.env.company.id)],
            order='sequence, start_time, id')

        machines = lines.mapped('workcenter_id')
        if not machines:
            machine_domain = [('active', '=', True)]
            if department_ids:
                machine_domain.append(('department_id', 'in', department_ids))
            machines = self.env['mrp.workcenter'].search(machine_domain)
        machines = machines.sorted(
            lambda m: (m.department_id.name or '', m.name or ''))

        dates = []
        day = date_from
        while day <= date_to:
            dates.append(day)
            day += timedelta(days=1)

        cells = {}
        for line in lines:
            key = '%s|%s|%s' % (line.workcenter_id.id, line.date,
                                line.shift_id.id)
            cell = cells.setdefault(key, {
                'hours': 0.0, 'qty': 0.0, 'lines': 0, 'products': [],
                'line_ids': [], 'capacity': 0.0, 'pct': 0.0,
            })
            cell['hours'] += line.planned_hours
            cell['qty'] += line.planned_qty
            cell['lines'] += 1
            cell['line_ids'].append(line.id)
            name = line.product_id.display_name
            if name not in cell['products']:
                cell['products'].append(name)

        for machine in machines:
            for day in dates:
                for shift in shifts:
                    key = '%s|%s|%s' % (machine.id, day, shift.id)
                    capacity = engine._slot_capacity_hours(machine, shift, day)
                    cell = cells.get(key)
                    if cell is None:
                        if capacity <= 0:
                            continue
                        cell = cells.setdefault(key, {
                            'hours': 0.0, 'qty': 0.0, 'lines': 0,
                            'products': [], 'line_ids': [],
                        })
                    cell['capacity'] = capacity
                    cell['pct'] = (
                        cell['hours'] / capacity * 100.0) if capacity else 0.0

        plan = self.browse(plan_id) if plan_id else self.browse()
        return {
            'dates': [fields.Date.to_string(d) for d in dates],
            'shifts': [{'id': s.id, 'code': s.code, 'name': s.name,
                        'net_hours': s.net_hours} for s in shifts],
            'machines': [{
                'id': m.id,
                'name': m.name,
                'code': m.fmes_machine_code or m.code or '',
                'department': m.department_id.name or '',
                'bottleneck': m.fmes_is_bottleneck,
            } for m in machines],
            'cells': cells,
            'plan': ({'id': plan.id, 'name': plan.name, 'state': plan.state}
                     if plan else None),
        }

    @api.model
    def move_plan_lines(self, line_ids, workcenter_id, date, shift_id):
        """Reassign plan lines to another machine-shift slot.

        Refuses a move that would overload the target, and says by how much.
        A board that lets a planner build an impossible plan is worse than no
        board at all.
        """
        lines = self.env['fmes.production.plan.line'].browse(line_ids)
        lines.check_access('write')
        if not lines:
            return {'ok': False, 'error': _("Nothing to move.")}

        machine = self.env['mrp.workcenter'].browse(workcenter_id)
        shift = self.env['fmes.shift'].browse(shift_id)
        date = fields.Date.to_date(date)
        engine = self.env['fmes.planning.engine']

        capacity = engine._slot_capacity_hours(machine, shift, date)
        if capacity <= 0:
            return {'ok': False, 'error': _(
                "%(machine)s has no capacity in that shift.",
                machine=machine.display_name)}

        existing = self.env['fmes.production.plan.line'].search([
            ('workcenter_id', '=', machine.id),
            ('date', '=', date),
            ('shift_id', '=', shift.id),
            ('state', '!=', 'cancelled'),
            ('id', 'not in', lines.ids),
        ])
        used = sum(existing.mapped('planned_hours'))

        # Re-size against the target machine's own rate: the same quantity
        # takes a different amount of time on a different machine.
        capacity_model = self.env['fmes.capacity.matrix']
        resized = []
        for line in lines:
            row = capacity_model._resolve(machine, line.product_id, date=date)
            rate = row.effective_output_per_hour if row else 0.0
            if not rate:
                return {'ok': False, 'error': _(
                    "%(machine)s has no capacity rate for %(product)s.",
                    machine=machine.display_name,
                    product=line.product_id.display_name)}
            # Setup time belongs to the machine being moved to, not the one
            # being moved from — a different machine has a different changeover.
            changeover = row.changeover_minutes or 0
            hours = line.planned_qty / rate + changeover / 60.0
            resized.append((line, rate, changeover, hours))

        needed = sum(item[3] for item in resized)
        if used + needed > capacity + 1e-6:
            return {'ok': False, 'error': _(
                "That slot would be overloaded: %(needed).2f h needed but only "
                "%(free).2f h free on %(machine)s.",
                needed=needed, free=max(capacity - used, 0.0),
                machine=machine.display_name)}

        for line, rate, changeover, hours in resized:
            line.write({
                'workcenter_id': machine.id,
                'date': date,
                'shift_id': shift.id,
                'output_rate': rate,
                'changeover_minutes': changeover,
                'planned_hours': hours,
                'planned_manpower': machine.fmes_get_std_manpower(
                    line.product_id, date=date),
                'source': 'manual' if line.source == 'auto' else line.source,
            })
        return {'ok': True, 'moved': len(resized)}


class FmesProductionPlanLine(models.Model):
    _name = 'fmes.production.plan.line'
    _description = 'Production Plan Line'
    _order = 'date, shift_id, workcenter_id, sequence, id'
    _check_company_auto = True

    plan_id = fields.Many2one(
        'fmes.production.plan', required=True, ondelete='cascade',
        index=True)
    company_id = fields.Many2one(
        related='plan_id.company_id', store=True, index=True)

    date = fields.Date(required=True, index=True)
    shift_id = fields.Many2one(
        'fmes.shift', required=True, index=True, check_company=True)
    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Machine', required=True, index=True,
        check_company=True)
    department_id = fields.Many2one(
        related='workcenter_id.department_id', store=True, index=True)
    product_id = fields.Many2one(
        'product.product', required=True, index=True)

    production_id = fields.Many2one(
        'mrp.production', string='Manufacturing Order', index=True,
        ondelete='set null')
    fmes_is_blocked = fields.Boolean(
        related='production_id.fmes_is_blocked', store=True, readonly=True,
        help="True when the source order is blocked (Requirement 4.2). "
             "False, not unknown, for a line with no source order.")
    workorder_id = fields.Many2one(
        'mrp.workorder', string='Work Order', index=True,
        ondelete='set null')
    date_deadline = fields.Date(
        string='Order Deadline',
        help="Deadline of the source order, copied at planning time so the "
             "plan stays meaningful if the order later changes.")

    planned_qty = fields.Float(
        required=True, digits='Product Unit of Measure')
    qty_done = fields.Float(
        string='Produced', digits='Product Unit of Measure', readonly=True,
        help="Filled in by production entries from Phase 4 onwards.")
    remaining_qty = fields.Float(
        compute='_compute_remaining_qty', store=True,
        digits='Product Unit of Measure',
        help="What still has to be made. Feeds the carry-forward run.")
    planned_hours = fields.Float(
        help="Machine hours this line consumes, including changeover.")
    changeover_minutes = fields.Integer(
        help="Setup time included in the planned hours.")
    planned_manpower = fields.Float(string='Manpower')
    output_rate = fields.Float(
        string='Rate / Hour', digits='Product Unit of Measure', readonly=True,
        help="Capacity-matrix rate used to size this line.")

    sequence = fields.Integer(default=10, help="Order within the shift.")
    priority = fields.Selection(
        [('0', 'Normal'), ('1', 'Urgent')], default='0', index=True)
    source = fields.Selection(
        [('auto', 'Planning Engine'),
         ('manual', 'Manual'),
         ('carry_forward', 'Carry Forward')],
        default='manual', required=True, index=True)
    carry_forward_from_id = fields.Many2one(
        'fmes.production.plan.line', string='Carried Forward From',
        ondelete='set null',
        help="The line whose shortfall produced this one.")
    state = fields.Selection(
        LINE_STATES, default='pending', required=True, index=True)
    note = fields.Text()

    _sql_constraints = [
        ('fmes_plan_line_qty_positive',
         'CHECK(planned_qty > 0)',
         'A plan line must have a quantity greater than zero.'),
    ]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('planned_qty', 'qty_done')
    def _compute_remaining_qty(self):
        for line in self:
            line.remaining_qty = max(line.planned_qty - line.qty_done, 0.0)

    @api.depends('workcenter_id', 'product_id', 'date', 'shift_id')
    def _compute_display_name(self):
        for line in self:
            line.display_name = '%s / %s / %s' % (
                line.date or '', line.workcenter_id.display_name or '',
                line.product_id.display_name or '')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _slot_datetimes(self):
        """Start and end datetimes of this line's shift slot, in UTC.

        Shift times are wall-clock times in the company's timezone; work order
        dates are stored in UTC, so the conversion has to happen here rather
        than being fudged with a fixed offset.
        """
        self.ensure_one()
        return self.shift_id._slot_datetimes(self.date)

    @api.onchange('workcenter_id', 'product_id', 'planned_qty', 'date')
    def _onchange_recompute_hours(self):
        """Keep hours honest when a planner edits a line by hand."""
        for line in self:
            if not (line.workcenter_id and line.product_id and line.planned_qty):
                continue
            rate = line.workcenter_id.fmes_get_output_rate(
                line.product_id, date=line.date)
            line.output_rate = rate
            changeover = line.changeover_minutes or 0
            if rate:
                line.planned_hours = line.planned_qty / rate + changeover / 60.0
            else:
                line.planned_hours = 0.0
                return {'warning': {
                    'title': _("No capacity rate"),
                    'message': _(
                        "%(machine)s has no standard output defined for "
                        "%(product)s, so the hours cannot be calculated. Add a "
                        "row to the capacity matrix.",
                        machine=line.workcenter_id.display_name,
                        product=line.product_id.display_name),
                }}
            line.planned_manpower = line.workcenter_id.fmes_get_std_manpower(
                line.product_id, date=line.date)

    def action_open_production(self):
        self.ensure_one()
        if not self.production_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production',
            'res_id': self.production_id.id,
            'view_mode': 'form',
        }
