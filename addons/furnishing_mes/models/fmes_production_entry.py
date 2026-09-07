# -*- coding: utf-8 -*-
"""Daily production entry.

Requirement 2 end to end, and the historical record behind Requirement 3.4.

One row is one machine, one shift, one product, one day — the same grain as a
production plan line, which is what makes planned versus actual a subtraction
rather than a reconciliation exercise.

Entries move draft → submitted → approved. Only approved entries reach reports
and dashboards: a figure the supervisor has not signed off is not something
management should be steering by, and it is why the approval step exists at all.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

ENTRY_STATES = [
    ('draft', 'Draft'),
    ('submitted', 'Submitted'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
]

# Fields a supervisor's approval freezes. Anything outside this list (notes,
# for instance) stays editable, because correcting a comment is not the same as
# quietly restating what a shift produced.
LOCKED_FIELDS = {
    'date', 'shift_id', 'workcenter_id', 'product_id',
    'planned_qty', 'actual_qty', 'rejected_qty',
    'run_hours', 'downtime_hours', 'actual_manpower',
    'production_id', 'workorder_id', 'plan_line_id',
}


class FmesProductionEntry(models.Model):
    _name = 'fmes.production.entry'
    _description = 'Daily Production Entry'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, shift_id, workcenter_id, id'
    _check_company_auto = True

    name = fields.Char(
        required=True, copy=False, readonly=True, default=lambda self: _('New'))

    # ------------------------------------------------------------------ slot
    date = fields.Date(
        required=True, index=True, tracking=True,
        default=fields.Date.context_today)
    shift_id = fields.Many2one(
        'fmes.shift', required=True, index=True, tracking=True,
        check_company=True)
    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Machine', required=True, index=True,
        tracking=True, check_company=True)
    department_id = fields.Many2one(
        related='workcenter_id.department_id', store=True, index=True)
    product_id = fields.Many2one(
        'product.product', required=True, index=True, tracking=True)

    # --------------------------------------------------------------- sources
    plan_line_id = fields.Many2one(
        'fmes.production.plan.line', string='Plan Line', index=True,
        ondelete='set null',
        help="The planned line this entry reports against. Approving the entry "
             "writes the produced quantity back, which is what lets unfinished "
             "work carry forward.")
    production_id = fields.Many2one(
        'mrp.production', string='Manufacturing Order', index=True,
        ondelete='set null')
    workorder_id = fields.Many2one(
        'mrp.workorder', string='Work Order', index=True, ondelete='set null')

    # ------------------------------------------------------------ quantities
    planned_qty = fields.Float(
        string='Target', digits='Product Unit of Measure', tracking=True,
        help="The shift target, taken from the released plan.")
    actual_qty = fields.Float(
        string='Produced', digits='Product Unit of Measure', tracking=True)
    rejected_qty = fields.Float(
        string='Rejected', digits='Product Unit of Measure', tracking=True,
        help="Feeds the quality factor of OEE. Without it OEE is overstated.")
    ok_qty = fields.Float(
        string='Good', compute='_compute_quantities', store=True,
        digits='Product Unit of Measure')
    variance_qty = fields.Float(
        string='Variance', compute='_compute_quantities', store=True,
        digits='Product Unit of Measure')
    achievement_pct = fields.Float(
        string='Achievement %', compute='_compute_quantities', store=True,
        aggregator=None,
        help="Produced against target on this row. No column total is offered: "
             "averaging percentages would weight a 10-unit row the same as a "
             "1,000-unit one, and summing them is meaningless. Correct "
             "aggregation is SUM(actual)/SUM(planned), which the report models "
             "do. Blank when no target was set — 'no target' and 'produced "
             "nothing' are different things.")
    has_target = fields.Boolean(
        compute='_compute_quantities', store=True,
        help="False when this shift had no planned target, so reports can tell "
             "an unplanned shift apart from a missed one.")

    # ----------------------------------------------------------------- hours
    run_hours = fields.Float(
        string='Run Hours', tracking=True,
        help="Productive time on this machine during the shift.")
    downtime_hours = fields.Float(
        string='Downtime Hours', tracking=True,
        help="Time lost during the shift. Phase 5 replaces this with the sum "
             "of coded downtime events, so every lost hour carries a reason.")
    available_hours = fields.Float(
        compute='_compute_hours', store=True,
        help="Net shift hours: the capacity this slot had.")
    utilization_pct = fields.Float(
        string='Utilisation %', compute='_compute_hours', store=True,
        aggregator=None)

    # ---------------------------------------------------------- efficiency
    std_output_qty = fields.Float(
        string='Standard Output', compute='_compute_standards', store=True,
        digits='Product Unit of Measure',
        help="What the capacity matrix says this machine should have made in "
             "the hours it actually ran.")
    efficiency_pct = fields.Float(
        string='Efficiency %', compute='_compute_standards', store=True,
        aggregator=None)

    # ------------------------------------------------------------- manpower
    std_manpower = fields.Float(
        string='Standard Manpower', compute='_compute_standards', store=True,
        readonly=False)
    actual_manpower = fields.Float(string='Actual Manpower', tracking=True)
    manpower_shortage = fields.Float(
        compute='_compute_standards', store=True,
        help="Standard minus actual. Feeds the manpower impact analysis.")
    operator_ids = fields.Many2many(
        'hr.employee', string='Operators')

    # -------------------------------------------------------------- workflow
    state = fields.Selection(
        ENTRY_STATES, default='draft', required=True, index=True,
        tracking=True)
    submitted_by = fields.Many2one('res.users', readonly=True, copy=False)
    submitted_on = fields.Datetime(readonly=True, copy=False)
    approved_by = fields.Many2one(
        'res.users', readonly=True, copy=False,
        groups='furnishing_mes.group_fmes_supervisor')
    approved_on = fields.Datetime(
        readonly=True, copy=False,
        groups='furnishing_mes.group_fmes_supervisor')
    rejection_reason = fields.Text(readonly=True, copy=False)

    import_batch_id = fields.Many2one(
        'fmes.import.batch', string='Import Batch', readonly=True,
        ondelete='set null', index=True,
        help="Set when the row came from a spreadsheet import, so a bad "
             "import can be reversed as a unit.")

    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company)
    note = fields.Text(string='Remarks')

    _sql_constraints = [
        ('fmes_entry_slot_uniq',
         'unique(date, shift_id, workcenter_id, product_id, company_id)',
         'There is already an entry for this machine, product and shift on '
         'this date. Edit that entry instead of creating a second one.'),
        ('fmes_entry_actual_positive',
         'CHECK(actual_qty >= 0)',
         'Produced quantity cannot be negative.'),
        ('fmes_entry_rejected_positive',
         'CHECK(rejected_qty >= 0)',
         'Rejected quantity cannot be negative.'),
        ('fmes_entry_hours_positive',
         'CHECK(run_hours >= 0 AND downtime_hours >= 0)',
         'Hours cannot be negative.'),
    ]

    # ==================================================================
    # Computes
    # ==================================================================
    @api.depends('planned_qty', 'actual_qty', 'rejected_qty')
    def _compute_quantities(self):
        for entry in self:
            entry.ok_qty = entry.actual_qty - entry.rejected_qty
            entry.variance_qty = entry.actual_qty - entry.planned_qty
            entry.has_target = bool(entry.planned_qty)
            entry.achievement_pct = (
                entry.actual_qty / entry.planned_qty * 100.0
                if entry.planned_qty else 0.0)

    @api.depends('shift_id', 'shift_id.net_hours', 'run_hours')
    def _compute_hours(self):
        for entry in self:
            available = entry.shift_id.net_hours or 0.0
            entry.available_hours = available
            entry.utilization_pct = (
                entry.run_hours / available * 100.0) if available else 0.0

    @api.depends('workcenter_id', 'product_id', 'date', 'run_hours',
                 'actual_qty', 'actual_manpower')
    def _compute_standards(self):
        capacity_model = self.env['fmes.capacity.matrix']
        for entry in self:
            row = capacity_model._resolve(
                entry.workcenter_id, entry.product_id, date=entry.date)
            rate = row.effective_output_per_hour if row else 0.0
            entry.std_output_qty = rate * entry.run_hours
            entry.efficiency_pct = (
                entry.actual_qty / entry.std_output_qty * 100.0
                if entry.std_output_qty else 0.0)
            entry.std_manpower = (
                row.std_manpower if row and row.std_manpower
                else entry.workcenter_id.fmes_std_manpower)
            entry.manpower_shortage = (
                entry.std_manpower - entry.actual_manpower)

    # ==================================================================
    # Constraints
    # ==================================================================
    @api.constrains('actual_qty', 'rejected_qty')
    def _check_rejected_within_actual(self):
        for entry in self:
            if entry.rejected_qty > entry.actual_qty:
                raise ValidationError(_(
                    "Rejected quantity (%(rejected).2f) cannot exceed the "
                    "quantity produced (%(actual).2f).",
                    rejected=entry.rejected_qty, actual=entry.actual_qty))

    @api.constrains('run_hours', 'downtime_hours', 'shift_id')
    def _check_hours_within_shift(self):
        """Hours reported cannot exceed the shift that contained them."""
        for entry in self:
            total = entry.run_hours + entry.downtime_hours
            limit = entry.shift_id.duration_hours or 0.0
            if limit and total > limit + 1e-6:
                raise ValidationError(_(
                    "%(machine)s on %(date)s: %(total).2f hours reported for a "
                    "%(limit).2f hour shift.",
                    machine=entry.workcenter_id.display_name,
                    date=entry.date, total=total, limit=limit))

    # ==================================================================
    # CRUD
    # ==================================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'fmes.production.entry') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        """Approved entries are the historical record and do not move.

        Requirement 3.4 depends on this: a report is only worth reading if the
        numbers behind it cannot be quietly restated after the fact. The Plant
        Manager can still unlock an entry, and the chatter records that it
        happened.
        """
        # Approving through a plain write would sidestep action_approve and
        # every check in it. The record rules do not catch this on their own:
        # Odoo validates them against the records as they are, not as they
        # would become.
        if vals.get('state') == 'approved' and not self._is_supervisor():
            raise AccessError(_(
                "Approving production entries is a supervisor's job."))

        locked = set(vals) & LOCKED_FIELDS
        if locked and not self.env.context.get('fmes_bypass_lock'):
            manager = self.env.user.has_group(
                'furnishing_mes.group_fmes_manager')
            frozen = self.filtered(lambda e: e.state == 'approved')
            if frozen and not manager:
                raise AccessError(_(
                    "%(entry)s has been approved and its figures are locked. "
                    "Ask a Plant Manager to reopen it if it needs correcting.",
                    entry=frozen[0].name))
        return super().write(vals)

    @api.onchange('workcenter_id', 'product_id', 'date', 'shift_id')
    def _onchange_slot(self):
        """Pull the shift target from the released plan."""
        for entry in self:
            if not (entry.workcenter_id and entry.product_id
                    and entry.date and entry.shift_id):
                continue
            line = entry._find_plan_line()
            if line:
                entry.plan_line_id = line.id
                entry.planned_qty = line.planned_qty
                entry.production_id = line.production_id.id
                entry.workorder_id = line.workorder_id.id

    def _find_plan_line(self):
        """The released plan line covering this slot, if there is one."""
        self.ensure_one()
        return self.env['fmes.production.plan.line'].search([
            ('date', '=', self.date),
            ('shift_id', '=', self.shift_id.id),
            ('workcenter_id', '=', self.workcenter_id.id),
            ('product_id', '=', self.product_id.id),
            ('state', '!=', 'cancelled'),
            ('plan_id.state', 'in', ('released', 'in_progress')),
        ], limit=1)

    # ==================================================================
    # Workflow
    # ==================================================================
    def action_submit(self):
        for entry in self:
            if entry.state not in ('draft', 'rejected'):
                raise UserError(_(
                    "%s has already been submitted.", entry.name))
            if entry.actual_qty <= 0 and entry.downtime_hours <= 0:
                raise UserError(_(
                    "%s reports neither production nor downtime. Record what "
                    "happened during the shift before submitting.", entry.name))
            entry.write({
                'state': 'submitted',
                'submitted_by': self.env.user.id,
                'submitted_on': fields.Datetime.now(),
                'rejection_reason': False,
            })

    def action_approve(self):
        self._check_supervisor()
        for entry in self:
            if entry.state != 'submitted':
                raise UserError(_(
                    "%s must be submitted before it can be approved.",
                    entry.name))
            entry.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'approved_on': fields.Datetime.now(),
            })
            entry._sync_plan_line()

    def action_reject(self):
        self._check_supervisor()
        for entry in self:
            if entry.state != 'submitted':
                raise UserError(_(
                    "Only a submitted entry can be rejected."))
            entry.state = 'rejected'

    def action_reset_to_draft(self):
        """Reopen an entry. Approved entries need a Plant Manager."""
        for entry in self:
            if entry.state == 'approved' and not self.env.user.has_group(
                    'furnishing_mes.group_fmes_manager'):
                raise AccessError(_(
                    "Only a Plant Manager can reopen an approved entry."))
            previous = entry.state
            entry.with_context(fmes_bypass_lock=True).write({
                'state': 'draft',
                'approved_by': False,
                'approved_on': False,
            })
            if previous == 'approved':
                entry._sync_plan_line()
                entry.message_post(body=_(
                    "Approved entry reopened for correction by %s.",
                    self.env.user.display_name))

    def _is_supervisor(self):
        """True for a supervisor, a manager, or an automated run.

        Superuser has to pass: crons and data loads legitimately approve
        entries, and a permission check that blocks the system from acting on
        its own behalf is a bug, not security.
        """
        return self.env.su or self.env.user.has_group(
            'furnishing_mes.group_fmes_supervisor')

    def _check_supervisor(self):
        if not self._is_supervisor():
            raise AccessError(_(
                "Approving production entries is a supervisor's job."))

    def _sync_plan_line(self):
        """Write approved output back onto the plan line.

        This is what closes the loop with Phase 3: unfinished work is the plan's
        quantity minus what was actually approved, and that difference is what
        carries forward into the next plan.
        """
        self.ensure_one()
        line = self.plan_line_id
        if not line:
            return
        approved = self.search([
            ('plan_line_id', '=', line.id),
            ('state', '=', 'approved'),
        ])
        produced = sum(approved.mapped('actual_qty'))
        state = line.state
        if produced <= 0:
            state = 'pending'
        elif produced + 1e-6 >= line.planned_qty:
            state = 'done'
        else:
            state = 'partial'
        line.write({'qty_done': produced, 'state': state})

    # ==================================================================
    # Generation from the plan
    # ==================================================================
    @api.model
    def _generate_from_plan(self, target_date=None, company=None):
        """Create draft entries for every released plan line on a date.

        Run by cron at the start of each day, so an operator arriving at the
        terminal finds their targets already there rather than typing them in.
        Idempotent: a slot that already has an entry is left alone.
        """
        company = company or self.env.company
        target_date = fields.Date.to_date(
            target_date or fields.Date.context_today(self))

        lines = self.env['fmes.production.plan.line'].search([
            ('date', '=', target_date),
            ('company_id', '=', company.id),
            ('state', 'not in', ('cancelled', 'done')),
            ('plan_id.state', 'in', ('released', 'in_progress')),
        ])
        if not lines:
            return self.browse()

        existing = self.search([
            ('date', '=', target_date),
            ('company_id', '=', company.id),
        ])
        taken = {
            (e.shift_id.id, e.workcenter_id.id, e.product_id.id)
            for e in existing
        }

        vals_list = []
        for line in lines:
            key = (line.shift_id.id, line.workcenter_id.id, line.product_id.id)
            if key in taken:
                continue
            taken.add(key)
            vals_list.append({
                'date': line.date,
                'shift_id': line.shift_id.id,
                'workcenter_id': line.workcenter_id.id,
                'product_id': line.product_id.id,
                'plan_line_id': line.id,
                'production_id': line.production_id.id,
                'workorder_id': line.workorder_id.id,
                'planned_qty': line.planned_qty,
                'std_manpower': line.planned_manpower,
                'company_id': line.company_id.id,
            })
        return self.create(vals_list) if vals_list else self.browse()

    @api.model
    def _cron_generate_daily_entries(self):
        """Scheduled action: prepare today's entries for every company."""
        for company in self.env['res.company'].search([]):
            self.with_company(company)._generate_from_plan(company=company)

    # ==================================================================
    # Actions
    # ==================================================================
    def action_open_plan_line(self):
        self.ensure_one()
        if not self.plan_line_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'fmes.production.plan.line',
            'res_id': self.plan_line_id.id,
            'view_mode': 'form',
        }
