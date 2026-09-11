# -*- coding: utf-8 -*-
"""Shop-floor terminal endpoints.

Every route re-derives what the calling user is allowed to touch from the
server's own view of their scope. Nothing here trusts a machine id, an entry id
or a quantity because the client sent it: the terminal runs on a shared tablet
on a factory floor, which is the least trustworthy client in the building.
"""

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from ..models.mrp_workcenter_productivity_loss import FMES_LOSS_CATEGORY

# Errors the operator caused (bad input, a busy machine, a missing remark) are
# reported back as a friendly {ok: False, error} rather than as a 500 — a
# tablet on the shop floor should never show a raw traceback.
_USER_FACING_ERRORS = (UserError, AccessError, ValidationError, ValueError)


class FmesShopFloor(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _allowed_workcenters(self):
        """Machines the current user may record on.

        Phase 8 adds the daily roster as a second source; this method is the
        only place that has to change.
        """
        user = request.env.user
        if user.has_group('furnishing_mes.group_fmes_supervisor'):
            return request.env['mrp.workcenter'].search(
                [('active', '=', True)])
        allowed = user.fmes_allowed_workcenter_ids
        if allowed:
            return allowed
        # Unscoped operator: may record anywhere, but the record rules still
        # limit them to their own entries.
        return request.env['mrp.workcenter'].search([('active', '=', True)])

    def _check_workcenter(self, workcenter_id):
        machine = request.env['mrp.workcenter'].browse(
            int(workcenter_id)).exists()
        if not machine or machine not in self._allowed_workcenters():
            raise AccessError(_(
                "You are not assigned to that machine."))
        return machine

    def _entry_for_user(self, entry_id):
        entry = request.env['fmes.production.entry'].browse(
            int(entry_id)).exists()
        if not entry:
            raise UserError(_("That entry no longer exists."))
        # Record rules decide visibility; this makes them do their job rather
        # than trusting the id that arrived from the tablet.
        entry.check_access('write')
        self._check_workcenter(entry.workcenter_id.id)
        return entry

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    @http.route('/fmes/terminal/machines', type='json', auth='user')
    def machines(self, **kwargs):
        """Machines the operator may pick from, with today's status."""
        machines = self._allowed_workcenters()
        return {
            'user': request.env.user.display_name,
            'scoped': request.env.user.fmes_has_machine_scope,
            # sudo() only for the live-status computes, and only for machines
            # already established as this user's. Operators hold no rights on
            # mrp.workorder or maintenance.request, which those computes read.
            'machines': [{
                'id': m.id,
                'name': m.name,
                'code': m.fmes_machine_code or m.code or '',
                'department': m.department_id.name or '',
                'state': m.sudo().fmes_current_state,
                'target': m.sudo().fmes_today_target,
                'produced': m.sudo().fmes_today_produced,
                'achievement': m.sudo().fmes_today_achievement,
            } for m in machines],
        }

    @http.route('/fmes/terminal/shifts', type='json', auth='user')
    def shifts(self, **kwargs):
        shifts = request.env['fmes.shift'].search(
            [('company_id', '=', request.env.company.id)],
            order='sequence, start_time, id')
        return [{
            'id': s.id, 'code': s.code, 'name': s.name,
            'range': s.time_range, 'net_hours': s.net_hours,
        } for s in shifts]

    @http.route('/fmes/terminal/board', type='json', auth='user')
    def board(self, workcenter_id, shift_id=None, date=None, **kwargs):
        """Everything the terminal shows for one machine and shift."""
        machine = self._check_workcenter(workcenter_id)
        Entry = request.env['fmes.production.entry']
        day = date or fields.Date.context_today(Entry)

        domain = [('workcenter_id', '=', machine.id), ('date', '=', day)]
        if shift_id:
            domain.append(('shift_id', '=', int(shift_id)))
        entries = Entry.search(domain)

        # The machine is already authorised above, so reading its work orders
        # with elevated rights is safe. Entries below stay on the user's own
        # rights, because the record rules are what scope them.
        workorders = request.env['mrp.workorder'].sudo().search([
            ('workcenter_id', '=', machine.id),
            ('state', 'not in', ('done', 'cancel')),
        ], order='date_start, id', limit=10)

        return {
            'machine': {
                'id': machine.id,
                'name': machine.name,
                'code': machine.fmes_machine_code or machine.code or '',
                'state': machine.sudo().fmes_current_state,
            },
            'date': str(day),
            'entries': [self._entry_payload(e) for e in entries],
            'workorders': [{
                'id': w.id,
                'name': w.name,
                'production': w.production_id.name,
                'product': w.production_id.product_id.display_name,
                'qty': w.qty_production,
                'produced': w.qty_produced,
                'state': w.state,
            } for w in workorders],
        }

    def _entry_payload(self, entry):
        return {
            'id': entry.id,
            'name': entry.name,
            'product': entry.product_id.display_name,
            'product_id': entry.product_id.id,
            'shift': entry.shift_id.code,
            'shift_id': entry.shift_id.id,
            'planned_qty': entry.planned_qty,
            'actual_qty': entry.actual_qty,
            'rejected_qty': entry.rejected_qty,
            'achievement': entry.achievement_pct,
            'has_target': entry.has_target,
            'run_hours': entry.run_hours,
            'downtime_hours': entry.downtime_hours,
            'actual_manpower': entry.actual_manpower,
            'state': entry.state,
            'editable': entry.state in ('draft', 'rejected'),
            'downtime_events': [
                self._downtime_payload(ev)
                # Own sudo() here is safe: the entry itself has already
                # passed the caller's own read access, and its linked events
                # are read-only display data for a screen the operator is
                # already authorised to be looking at.
                for ev in entry.sudo().productivity_ids.sorted(
                    lambda e: e.date_start, reverse=True)
            ],
        }

    def _downtime_payload(self, event):
        return {
            'id': event.id,
            'loss_id': event.loss_id.id,
            'loss_name': event.loss_id.name,
            'category': event.fmes_category,
            'remarks': event.fmes_remarks or '',
            'date_start': fields.Datetime.to_string(event.date_start),
            'date_end': fields.Datetime.to_string(event.date_end)
            if event.date_end else None,
            'duration_minutes': event.duration,
            'running': event.fmes_is_running,
            'state': event.fmes_state,
        }

    @http.route('/fmes/terminal/record', type='json', auth='user')
    def record(self, entry_id, values, **kwargs):
        """Save what the operator typed.

        Only the fields an operator is allowed to touch are accepted; anything
        else in the payload is ignored rather than trusted.

        The whole body runs inside one try/except, not just the write() call.
        Odoo does not always validate a record's constraints synchronously
        inside write()/create() -- some are only checked at the next point
        something forces a flush, which can be a later field read. Building
        the JSON response reads fields on the record just written, so a
        constraint violation can surface there instead of at the write()
        line. A tablet on the shop floor gets {'ok': False, 'error'} either
        way, never a raw exception.
        """
        try:
            entry = self._entry_for_user(entry_id)
            if entry.state not in ('draft', 'rejected'):
                return {'ok': False,
                        'error': _("This entry has already been submitted.")}

            # downtime_hours is deliberately not in this whitelist from
            # Phase 5 onward: it is kept in step automatically from coded
            # downtime events (see the downtime/* routes below), not typed
            # directly.
            allowed = {'actual_qty', 'rejected_qty', 'run_hours',
                       'actual_manpower', 'note'}
            payload = {k: v for k, v in (values or {}).items()
                      if k in allowed}
            if not payload:
                return {'ok': False, 'error': _("Nothing to save.")}
            entry.write(payload)
            result = {'ok': True, 'entry': self._entry_payload(entry)}
        except _USER_FACING_ERRORS as exc:
            return {'ok': False, 'error': str(exc)}
        return result

    @http.route('/fmes/terminal/submit', type='json', auth='user')
    def submit(self, entry_ids, **kwargs):
        """Submit a shift's entries for supervisor approval."""
        try:
            entries = request.env['fmes.production.entry'].browse(
                [int(i) for i in entry_ids]).exists()
            for entry in entries:
                self._entry_for_user(entry.id)
            entries.action_submit()
        except _USER_FACING_ERRORS as exc:
            return {'ok': False, 'error': str(exc)}
        return {'ok': True, 'submitted': len(entries)}

    @http.route('/fmes/terminal/create_entry', type='json', auth='user')
    def create_entry(self, workcenter_id, shift_id, product_id, date=None,
                     **kwargs):
        """Add a line for something produced that was not planned."""
        try:
            machine = self._check_workcenter(workcenter_id)
            Entry = request.env['fmes.production.entry']
            day = date or fields.Date.context_today(Entry)
            entry = Entry.create({
                'date': day,
                'shift_id': int(shift_id),
                'workcenter_id': machine.id,
                'product_id': int(product_id),
            })
            result = {'ok': True, 'entry': self._entry_payload(entry)}
        except _USER_FACING_ERRORS as exc:
            return {'ok': False, 'error': str(exc)}
        return result

    @http.route('/fmes/terminal/products', type='json', auth='user')
    def products(self, workcenter_id, **kwargs):
        """Products this machine has a capacity rate for."""
        machine = self._check_workcenter(workcenter_id)
        rows = request.env['fmes.capacity.matrix'].sudo().search([
            ('workcenter_id', '=', machine.id), ('active', '=', True)])
        products = request.env['product.product']
        for row in rows:
            if row.product_id:
                products |= row.product_id
            elif row.product_category_id:
                products |= products.search(
                    [('categ_id', 'child_of', row.product_category_id.id)],
                    limit=40)
        return [{'id': p.id, 'name': p.display_name} for p in products[:60]]

    @http.route('/fmes/terminal/material_check', type='json', auth='user')
    def material_check(self, product_id, qty=1, **kwargs):
        """Is there enough of each BOM component on hand for `qty` units?

        Informational, not a hard gate — an operator can still start
        production even if a component reads short (the plant may know a
        delivery is on its way, or count what the terminal cannot see). A
        product with no BOM at all reports `no_bom: True` rather than a
        false "all clear": nothing to check is different from everything
        being in stock.
        """
        product = request.env['product.product'].sudo().browse(
            int(product_id)).exists()
        if not product:
            return {'no_bom': True, 'components': [], 'all_available': True}

        qty = float(qty) or 1.0
        bom = request.env['mrp.bom'].sudo()._bom_find(
            product, company_id=request.env.company.id).get(product)
        if not bom:
            return {'no_bom': True, 'components': [], 'all_available': True}

        # BOM quantities are per `bom.product_qty` units of finished good;
        # scale each line to what producing `qty` actually needs.
        factor = qty / bom.product_qty if bom.product_qty else 0.0
        components = []
        all_available = True
        for line in bom.bom_line_ids:
            required = line.product_qty * factor
            available = line.product_id.qty_available
            ok = available >= required
            all_available = all_available and ok
            components.append({
                'name': line.product_id.display_name,
                'required': required,
                'available': available,
                'uom': line.product_uom_id.name,
                'ok': ok,
            })
        return {
            'no_bom': False,
            'components': components,
            'all_available': all_available,
        }

    # ------------------------------------------------------------------
    # Downtime — reason picker, running timer (Requirement 6)
    # ------------------------------------------------------------------
    @http.route('/fmes/terminal/downtime/reasons', type='json', auth='user')
    def downtime_reasons(self, **kwargs):
        """Loss reasons grouped by category, for the terminal's reason grid.

        Only categorised reasons are offered — never an uncategorised one,
        so an operator cannot even choose to log downtime with no reason.
        Odoo's own "Fully Productive Time" entry (loss_type='productive') is
        never a downtime reason and is excluded.
        """
        Loss = request.env['mrp.workcenter.productivity.loss'].sudo()
        reasons = Loss.search([
            ('loss_type', '!=', 'productive'),
            ('fmes_category', '!=', False),
        ], order='sequence, id')

        by_category = {}
        for reason in reasons:
            by_category.setdefault(reason.fmes_category, []).append({
                'id': reason.id,
                'name': reason.name,
                'requires_remark': reason.fmes_category == 'other',
            })

        # FMES_LOSS_CATEGORY carries the display order and labels already
        # used everywhere else in the module — one source of truth, not a
        # second copy of the same ten strings.
        return [{
            'category': key,
            'label': label,
            'reasons': by_category[key],
        } for key, label in FMES_LOSS_CATEGORY if key in by_category]

    @http.route('/fmes/terminal/downtime/start', type='json', auth='user')
    def downtime_start(self, entry_id, loss_id, remarks=None, **kwargs):
        """Start the timer: one open event, tied to one entry.

        The model itself validates the reason/remark rule synchronously in
        create() (see FmesWorkcenterProductivity._fmes_validate_downtime_rules)
        rather than relying solely on api.constrains, so this try/except is
        guaranteed to actually catch it — see that method's docstring for why
        api.constrains alone was not reliable enough here (Phase 5, D5.4).
        """
        try:
            entry = self._entry_for_user(entry_id)
            event = request.env['mrp.workcenter.productivity'].create({
                'workcenter_id': entry.workcenter_id.id,
                'loss_id': int(loss_id),
                'fmes_entry_id': entry.id,
                'fmes_remarks': remarks or False,
                'date_start': fields.Datetime.now(),
            })
            result = {'ok': True, 'event': self._downtime_payload(event),
                     'entry': self._entry_payload(entry)}
        except _USER_FACING_ERRORS as exc:
            return {'ok': False, 'error': str(exc)}
        return result

    @http.route('/fmes/terminal/downtime/stop', type='json', auth='user')
    def downtime_stop(self, event_id, remarks=None, **kwargs):
        """Stop the timer. A remark for 'Other' can be supplied here too,
        since the operator often only knows what to write once it is over.

        Whole body in one try/except — see the note on record() for why:
        building the response reads fields on the just-written record, and a
        deferred constraint check can surface there rather than at write().
        """
        try:
            event = request.env['mrp.workcenter.productivity'].browse(
                int(event_id)).exists()
            if not event:
                return {'ok': False,
                        'error': _("That downtime event no longer exists.")}
            self._check_workcenter(event.workcenter_id.id)
            if not event.fmes_is_running:
                return {'ok': False,
                        'error': _("That event has already been stopped.")}
            vals = {'date_end': fields.Datetime.now()}
            if remarks:
                vals['fmes_remarks'] = remarks
            event.write(vals)
            result = {'ok': True, 'event': self._downtime_payload(event),
                     'entry': self._entry_payload(event.fmes_entry_id)
                     if event.fmes_entry_id else None}
        except _USER_FACING_ERRORS as exc:
            return {'ok': False, 'error': str(exc)}
        return result
