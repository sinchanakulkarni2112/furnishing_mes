# -*- coding: utf-8 -*-
"""Downtime events.

Requirement 6 in full. Odoo already models a stoppage as
`mrp.workcenter.productivity` — start time, end time, a loss reason — and
`mrp.workcenter._compute_oee()` reads it directly. We extend that model rather
than building a parallel one (ADR-001): a separate downtime log would leave
Odoo's own OEE permanently blind to what this module records.

What we add on top: the shift and production-entry it happened in, the plant's
own loss category (already on the reason, from Phase 2), a supervisor
approval workflow, and automatic escalation to maintenance for reasons that
call for it.

Approval workflow
------------------
`fmes_state`: draft -> approved (supervisor) or rejected (supervisor).
Rejecting sets it straight back to draft — a rejected event *is* an editable
one, so "returns it to the operator" needs no separate resubmit step. If an
operator then edits a rejected record, the edit itself clears the rejection
and returns it to plain draft, so it re-enters the queue without extra clicks.

Once approved, an event is locked the same way an approved production entry
is (Phase 4, D4.1/D4.2): duration-affecting fields cannot be changed except by
a Plant Manager reopening it, and writing `fmes_state='approved'` directly
(bypassing `action_approve`) is refused so `fmes_approved_by`/`_on` can never
be missing on an approved record.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

DOWNTIME_STATES = [
    ('draft', 'Draft'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
]

# Fields that stop moving once a downtime event is approved. Remarks are
# deliberately excluded, same reasoning as the production entry: correcting a
# comment is not restating what happened.
LOCKED_FIELDS = {
    'loss_id', 'workcenter_id', 'workorder_id', 'production_id',
    'date_start', 'date_end', 'fmes_entry_id', 'fmes_shift_id',
}


class MrpWorkcenterProductivity(models.Model):
    _inherit = ['mrp.workcenter.productivity', 'mail.thread']
    _name = 'mrp.workcenter.productivity'

    fmes_entry_id = fields.Many2one(
        'fmes.production.entry', string='Production Entry', index=True,
        ondelete='set null',
        help="The shift entry this stoppage interrupted. Set automatically "
             "when logged from the Shop-Floor Terminal.")
    fmes_shift_id = fields.Many2one(
        'fmes.shift', string='Shift', index=True,
        related='fmes_entry_id.shift_id', store=True, readonly=True)
    fmes_category = fields.Selection(
        related='loss_id.fmes_category', store=True, readonly=True,
        string='Loss Category', index=True,
        help="The plant's own downtime classification, for reporting. "
             "Odoo's 'Effectiveness' stays separate because OEE depends on it.")
    fmes_remarks = fields.Text(
        string='Remarks',
        help="Required when the reason is 'Other'.")
    fmes_reported_by = fields.Many2one(
        'res.users', string='Reported By', default=lambda self: self.env.user,
        readonly=True)
    fmes_state = fields.Selection(
        DOWNTIME_STATES, string='Review Status', default='draft',
        required=True, index=True, tracking=True)
    fmes_approved_by = fields.Many2one(
        'res.users', readonly=True, copy=False,
        groups='furnishing_mes.group_fmes_supervisor')
    fmes_approved_on = fields.Datetime(
        readonly=True, copy=False,
        groups='furnishing_mes.group_fmes_supervisor')
    fmes_maintenance_request_id = fields.Many2one(
        'maintenance.request', string='Maintenance Request', readonly=True,
        copy=False, ondelete='set null',
        help="Raised automatically when the loss reason is flagged to "
             "require maintenance.")
    fmes_is_running = fields.Boolean(
        compute='_compute_fmes_is_running', search='_search_fmes_is_running',
        string='Running',
        help="True while the stoppage has a start time but no end time yet.")

    # ==================================================================
    # Computes
    # ==================================================================
    @api.depends('date_start', 'date_end')
    def _compute_fmes_is_running(self):
        for event in self:
            event.fmes_is_running = bool(event.date_start and not event.date_end)

    def _search_fmes_is_running(self, operator, value):
        running = (operator == '=' and value) or (operator == '!=' and not value)
        domain = [('date_start', '!=', False), ('date_end', '=', False)]
        if running:
            return domain
        return ['!'] + domain if domain else []

    # ==================================================================
    # Constraints
    # ==================================================================
    #
    # The two categorisation rules below are enforced TWICE: once early and
    # synchronously in create()/write() (_fmes_validate_downtime_rules,
    # further down — this is the gate that actually matters), and again here
    # as an api.constrains backstop.
    #
    # The early check exists because relying on api.constrains alone proved
    # unsafe (Phase 5, D5.4): both rules read `fmes_category`, a computed
    # (related, stored) field. On a model with mail.thread's tracking
    # enabled, Odoo can defer that field's recompute-and-validate cycle past
    # create()/write() returning, to the framework's own next flush — which,
    # for a JSON-RPC controller, happens in Odoo's HTTP retry/transactioning
    # wrapper, AFTER the controller has already returned. A ValidationError
    # raised there is outside any try/except the controller can write, so an
    # operator's tablet would see a raw server error instead of the friendly
    # message the constraint carries. Found by a downtime/start request that
    # correctly caught and returned {'ok': False, ...} for this exact
    # violation, and STILL surfaced an uncaught ValidationError moments
    # later, traced to mail.thread's own _compute_field_value calling
    # _validate_fields during the HTTP layer's post-dispatch env.cr.flush().
    #
    # The third constraint below (_check_one_open_event_per_machine) has no
    # such problem: it depends only on plain, directly-written fields with
    # no computed component, so Odoo validates it synchronously inside
    # create()/write() every time, and needs no early counterpart.
    @api.constrains('loss_id', 'fmes_category')
    def _check_downtime_is_categorised(self):
        """No uncategorised bucket (Phase 5 exit criterion)."""
        for event in self:
            if event.loss_id.loss_type != 'productive' and not event.fmes_category:
                raise ValidationError(_(
                    "%(reason)s has no downtime category assigned. Ask a "
                    "Plant Manager to classify it under Configuration > "
                    "Downtime Reasons before it can be logged.",
                    reason=event.loss_id.name))

    @api.constrains('fmes_category', 'fmes_remarks')
    def _check_other_has_remarks(self):
        for event in self:
            if event.fmes_category == 'other' and not (
                    event.fmes_remarks and event.fmes_remarks.strip()):
                raise ValidationError(_(
                    "A remark is required when the downtime reason is "
                    "'Other', so the record is still useful without it."))

    @api.model
    def _fmes_validate_downtime_rules(self, loss_id, remarks):
        """Early, synchronous version of the two rules above.

        Reads the loss reason's category directly rather than through the
        computed `fmes_category` field, so it needs no flush and cannot be
        deferred: it either raises right here, in the caller's own call
        stack, or it does not raise at all.
        """
        if not loss_id:
            return
        loss = self.env['mrp.workcenter.productivity.loss'].browse(loss_id)
        if loss.loss_type != 'productive' and not loss.fmes_category:
            raise ValidationError(_(
                "%(reason)s has no downtime category assigned. Ask a Plant "
                "Manager to classify it under Configuration > Downtime "
                "Reasons before it can be logged.", reason=loss.name))
        if loss.fmes_category == 'other' and not (
                remarks and remarks.strip()):
            raise ValidationError(_(
                "A remark is required when the downtime reason is 'Other', "
                "so the record is still useful without it."))

    @api.constrains('workcenter_id', 'date_start', 'date_end')
    def _check_one_open_event_per_machine(self):
        """A machine cannot be down for two reasons at the same moment.

        Only one running (date_end empty) event per machine at a time — this
        is what lets the terminal show a single, unambiguous timer.
        """
        for event in self.filtered(lambda e: not e.date_end):
            other_open = self.search([
                ('id', '!=', event.id),
                ('workcenter_id', '=', event.workcenter_id.id),
                ('date_end', '=', False),
            ], limit=1)
            if other_open:
                raise ValidationError(_(
                    "%(machine)s already has an open downtime event (%(other)s "
                    "started at %(when)s). Stop it before starting another.",
                    machine=event.workcenter_id.display_name,
                    other=other_open.loss_id.name,
                    when=other_open.date_start))

    # ==================================================================
    # CRUD
    # ==================================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._fmes_validate_downtime_rules(
                vals.get('loss_id'), vals.get('fmes_remarks'))
        records = super().create(vals_list)
        records._fmes_escalate_if_required()
        records._fmes_touch_entry_downtime()
        return records

    def write(self, vals):
        # Approving must go through action_approve(), which stamps who and
        # when. A direct write is the same hole D4.2 found on production
        # entries: record rules see the record as it is now, not as the
        # write would make it.
        if vals.get('fmes_state') == 'approved' and not self._is_supervisor():
            raise AccessError(_(
                "Approving downtime events is a supervisor's job."))

        # A rejected record becomes editable again the moment it is edited —
        # that IS "returned to the operator." Supervisors correcting a
        # rejected record themselves are exempt: they may want to fix and
        # approve it in the same motion.
        if (set(vals) & (LOCKED_FIELDS | {'fmes_remarks', 'fmes_category'})
                and 'fmes_state' not in vals
                and not self._is_supervisor()):
            rejected = self.filtered(lambda e: e.fmes_state == 'rejected')
            if rejected:
                vals = dict(vals, fmes_state='draft')

        locked = set(vals) & LOCKED_FIELDS
        if locked and not self.env.context.get('fmes_bypass_lock'):
            manager = self.env.user.has_group(
                'furnishing_mes.group_fmes_manager')
            frozen = self.filtered(lambda e: e.fmes_state == 'approved')
            if frozen and not manager:
                raise AccessError(_(
                    "This downtime event has been approved and is locked. "
                    "Ask a Plant Manager to reopen it if it needs correcting."))

        # fmes_state is handled by the caller's own write below; the approval
        # stamp fields are handled separately afterward, via sudo(). They are
        # supervisor-only at the field level (groups=), so an operator's own
        # write() — including the auto-revert-to-draft above — must never
        # carry them in its vals, even to clear them to False, or Odoo
        # refuses the whole write with an AccessError before it even looks
        # at the field's value.
        approving = vals.get('fmes_state') == 'approved'
        clearing_approval = 'fmes_state' in vals and not approving

        # Same early, synchronous check as create() — see the long comment
        # above _fmes_validate_downtime_rules for why this cannot be left to
        # api.constrains alone. Only worth doing when this write could
        # actually change the answer.
        if 'loss_id' in vals or 'fmes_remarks' in vals:
            for event in self:
                self._fmes_validate_downtime_rules(
                    vals.get('loss_id', event.loss_id.id),
                    vals.get('fmes_remarks', event.fmes_remarks))

        res = super().write(vals)

        if approving:
            self.sudo().write({'fmes_approved_by': self.env.user.id,
                               'fmes_approved_on': fields.Datetime.now()})
        elif clearing_approval:
            self.sudo().write({'fmes_approved_by': False,
                               'fmes_approved_on': False})

        if 'date_end' in vals or 'duration' in vals:
            self.mapped('fmes_entry_id')._fmes_recompute_downtime_hours()
        return res

    def _is_supervisor(self):
        return self.env.su or self.env.user.has_group(
            'furnishing_mes.group_fmes_supervisor')

    # ==================================================================
    # Workflow
    # ==================================================================
    def action_approve(self):
        for event in self:
            if not self._is_supervisor():
                raise AccessError(_(
                    "Approving downtime events is a supervisor's job."))
            if event.fmes_is_running:
                raise UserError(_(
                    "%s is still running and cannot be approved until it "
                    "has an end time.", event.loss_id.name))
            event.write({'fmes_state': 'approved'})

    def action_reject(self, reason=None):
        for event in self:
            if not self._is_supervisor():
                raise AccessError(_(
                    "Rejecting downtime events is a supervisor's job."))
            event.with_context(fmes_bypass_lock=True).write(
                {'fmes_state': 'rejected'})
            # The chatter note is best-effort. It must never be able to
            # undo an otherwise legitimate rejection just because, say, the
            # acting user has no email address configured and mail.thread
            # (or the sms module layered on top of it) refuses to post on
            # their behalf. Found by running this end to end with a
            # freshly-created demo user that had no email set.
            try:
                event.message_post(body=_(
                    "Rejected by %(user)s.%(reason)s",
                    user=self.env.user.display_name,
                    reason=(': ' + reason) if reason else ''))
            except UserError:
                pass

    def action_reset_to_draft(self):
        for event in self:
            if event.fmes_state == 'approved' and not self.env.user.has_group(
                    'furnishing_mes.group_fmes_manager'):
                raise AccessError(_(
                    "Only a Plant Manager can reopen an approved downtime "
                    "event."))
            event.with_context(fmes_bypass_lock=True).write(
                {'fmes_state': 'draft'})

    # ==================================================================
    # Auto-escalation (Requirement 6, deliverable 4)
    # ==================================================================
    def _fmes_escalate_if_required(self):
        """Raise a maintenance request for reasons flagged to need one.

        Runs at creation, not at approval: a broken machine needs someone
        walking over to it immediately, not after a supervisor's paperwork
        review. One request per event — each occurrence is a real breakdown
        occurrence, not a duplicate to be merged away.
        """
        for event in self:
            if not event.loss_id.fmes_requires_maintenance:
                continue
            if event.fmes_maintenance_request_id:
                continue
            equipment = event.workcenter_id.equipment_id
            if not equipment:
                event.message_post(body=_(
                    "This reason normally raises a maintenance request "
                    "automatically, but %(machine)s has no linked "
                    "maintenance equipment, so none was created.",
                    machine=event.workcenter_id.display_name))
                continue
            request = self.env['maintenance.request'].sudo().create({
                'name': _(
                    "%(reason)s: %(machine)s",
                    reason=event.loss_id.name,
                    machine=event.workcenter_id.display_name),
                'equipment_id': equipment.id,
                'workcenter_id': event.workcenter_id.id,
                'fmes_productivity_id': event.id,
                'maintenance_type': 'corrective',
                'maintenance_team_id': self._fmes_default_maintenance_team().id,
                'description': event.fmes_remarks or event.loss_id.name,
            })
            event.with_context(fmes_bypass_lock=True).write(
                {'fmes_maintenance_request_id': request.id})

    def _fmes_default_maintenance_team(self):
        """The team escalated requests are raised against.

        Prefers the team this module seeds (`data/fmes_maintenance_team.xml`,
        assumption A21 — one in-house team). Falls back to any team that
        exists, so a plant that deleted or renamed ours still gets a working
        escalation rather than a crash. `maintenance.team` has no other
        record on a production install: Odoo core only seeds one through its
        *demo* data, which a production install never loads.
        """
        Team = self.env['maintenance.team'].sudo()
        seeded = self.env.ref(
            'furnishing_mes.fmes_maintenance_team_default',
            raise_if_not_found=False)
        return seeded or Team.search([], limit=1)

    # ==================================================================
    # Entry rollup (Phase 4 deliverable 7)
    # ==================================================================
    def _fmes_touch_entry_downtime(self):
        entries = self.mapped('fmes_entry_id')
        if entries:
            entries._fmes_recompute_downtime_hours()

    def action_open_maintenance_request(self):
        self.ensure_one()
        if not self.fmes_maintenance_request_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'maintenance.request',
            'res_id': self.fmes_maintenance_request_id.id,
            'view_mode': 'form',
        }
