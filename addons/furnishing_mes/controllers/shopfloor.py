# -*- coding: utf-8 -*-
"""Shop-floor terminal endpoints.

Every route re-derives what the calling user is allowed to touch from the
server's own view of their scope. Nothing here trusts a machine id, an entry id
or a quantity because the client sent it: the terminal runs on a shared tablet
on a factory floor, which is the least trustworthy client in the building.
"""

import hmac

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from ..models.mrp_workcenter_productivity_loss import FMES_LOSS_CATEGORY

# Errors the operator caused (bad input, a busy machine, a missing remark) are
# reported back as a friendly {ok: False, error} rather than as a 500 — a
# tablet on the shop floor should never show a raw traceback.
_USER_FACING_ERRORS = (UserError, AccessError, ValidationError, ValueError)


class FmesShopFloor(http.Controller):

    # A 4-6 digit PIN is a low-entropy secret and the tablet is reachable by
    # the whole shift, so guessing must not be unlimited. Five tries is
    # forgiving enough that nobody locks themselves out over a typo and
    # tight enough that a four-digit space cannot be walked overnight.
    _PIN_MAX_ATTEMPTS = 5

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _active_employee(self):
        """The employee the shared tablet is currently recording for.

        A successful PIN switch (see `pin_verify`) stores the operator's
        employee id in the session, so subsequent terminal calls can attribute
        this tablet's writes to that employee without logging the Odoo session
        out. Falls back to the logged-in user's own employee, which is exactly
        the pre-switch behaviour.

        `hr.employee` is not readable by a shop-floor operator (its `pin`
        field is `groups='hr.group_hr_user'` -- verified: a `read(['pin'])` as
        an operator raises AccessError), so the lookup is `sudo()`ed. That is
        deliberate, not lazy: this endpoint's whole job is to re-read the
        operator id the PIN gate itself stored. The employee's PIN is never
        returned to the client, never logged and never stored by this module.
        """
        emp_id = request.session.get('fmes_active_employee_id')
        if emp_id:
            emp = request.env['hr.employee'].sudo().browse(emp_id).exists()
            if emp and emp.active:
                return emp
        return request.env.user.sudo().employee_id

    def _active_user(self):
        """The `res.users` to stamp as acting when the PIN is switched.

        The PIN gate stores the switched operator's user id when that employee
        has one (`fmes_active_user_id`). A factory worker may have a PIN but no
        Odoo login at all -- then the shared login keeps acting, and only the
        employee-level attribution fields record who was on the tablet.
        """
        uid = request.session.get('fmes_active_user_id')
        if uid:
            return request.env['res.users'].sudo().browse(uid).exists()
        return request.env.user

    def _pin_employees(self):
        """Every active employee with a PIN, most likely to be ours first.

        A shared tablet must accept any active employee's PIN (the whole point
        of the switch), but on the 4-digit collision -- two employees happen
        to share a PIN -- the calling user's own employee is tried first, so
        the tablet favours "same person" over "startled colleague". `pin` is
        `groups='hr.group_hr_user'` and the operator may not read it through
        the ORM, hence `sudo()`; the values are compared on the server and
        never exposed.
        """
        employees = request.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('pin', '!=', False),
        ])
        own = request.env.user.sudo().employee_id
        if own in employees:
            return own | (employees - own)
        return employees

    def _allowed_workcenters(self, employee=None):
        """Machines the current operator may record on.

        `employee` is the PIN-switched operator when the tablet has switched
        (see `pin_verify`); the machine list is then scoped by *that*
        employee's own user scope (their `fmes_allowed_workcenter_ids`, which
        itself reflects `fmes_workcenter_ids` / `fmes_department_ids`) rather
        than the shared Odoo login's. With no switch, `employee` falls back to
        the session user's own employee and the scope is unchanged.

        Phase 8 adds the daily roster as a second source; this method is the
        only place that has to change.
        """
        user = request.env.user
        if user.has_group('furnishing_mes.group_fmes_supervisor'):
            return request.env['mrp.workcenter'].search(
                [('active', '=', True)])
        employee = employee or self._active_employee()
        scoped_user = employee.user_id if employee and employee.user_id else user
        allowed = scoped_user.fmes_allowed_workcenter_ids
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
        """Machines the operator may pick from, with today's status.

        After a PIN switch the tablet reads as the switched employee: the
        header name is theirs and the machine list is scoped by their own
        access, not the shared Odoo login's. Without a switch nothing changes.
        """
        employee = self._active_employee()
        scoped_user = (employee.user_id if employee and employee.user_id
                       else request.env.user)
        machines = self._allowed_workcenters(employee)
        # The header name on a switched tablet is the operator's, so the
        # machine picker shows who is about to record, not who is logged in.
        emp_id = request.session.get('fmes_active_employee_id')
        user_name = (employee.name if (emp_id and employee)
                     else request.env.user.display_name)
        return {
            'user': user_name,
            'scoped': scoped_user.fmes_has_machine_scope,
            # sudo() only for the live-status computes, and only for machines
            # already established as this operator's. Operators hold no rights
            # on mrp.workorder or maintenance.request, which those computes
            # read.
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
            'stage': event.fmes_stage,
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
            # When the tablet has a PIN-switched operator, record who was on
            # it (fmes_operator_id). The stamp is a separate sudo() write
            # because attaching an hr.employee record requires reading it,
            # which operators may not do through the ORM.
            operator = self._active_employee()
            if operator:
                entry.sudo().write({'fmes_operator_id': operator.id})
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
            # A PIN-switched operator submits as themselves (submitted_by is
            # the native audit field), so their supervisor sees who actually
            # signed the shift off.
            operator_user_id = (self._active_employee().user_id.id
                                or request.env.uid)
            entries.action_submit(operator_user_id=operator_user_id)
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
            operator = self._active_employee()
            if operator:
                entry.sudo().write({'fmes_operator_id': operator.id})
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

    @http.route('/fmes/terminal/pin_verify', type='json', auth='user')
    def pin_verify(self, pin=None, **kwargs):
        """Confirm a typed PIN and switch the tablet's active operator.

        Shared-tablet multi-operator switch: any active employee whose PIN
        matches becomes the operator this tablet records for, without logging
        the Odoo session out (the shared login stays whoever logged the tablet
        into Odoo; the *operator* changes). When two employees share a PIN the
        calling user's own employee is preferred, so the tablet never hijacks
        somebody's session by accident on a 4-digit collision.

        Nothing else about the gate loosens:
          - five wrong attempts lock the gate until the next login
            (`fmes_pin_failures`), because a four-digit space must not be
            walkable on a tablet the whole shift can reach;
          - `pin_provisioned` means "some active employee has a PIN to check
            at all" — with no PIN provisioned anywhere the route refuses
            rather than pretending a check happened.

        Every answer carries the same keys — `ok`, `provisioned` (alias kept
        for the existing client), `pin_provisioned`, `locked`,
        `remaining_attempts` and `error` — so the client can branch without
        guessing which key missing means what. On success it also carries the
        switched operator's `employee_id`, `employee_name` and `user_id`.

        The PINs compared here are Odoo's own `hr.employee.pin` / the related
        `res.users.pin`; there is exactly one stored value (verified: the
        `res.users.pin` field is `related='employee_id.pin'`). This module
        stores no PIN of its own. `hr.employee.pin` is `groups='hr.group_hr_user'`,
        which an operator may not read through the ORM (verified: a direct
        read raises AccessError), so the search is `sudo()`ed — comparing the
        typed digits against a value the caller could not read is the endpoint's
        job, and the value never leaves the server.
        """
        employees = self._pin_employees()
        provisioned = bool(employees)
        attempts = request.session.get('fmes_pin_failures', 0)

        def remaining(attempts):
            return max(0, self._PIN_MAX_ATTEMPTS - attempts)

        def refuse(error, counted=True):
            failures = attempts
            if counted and provisioned:
                failures = request.session['fmes_pin_failures'] = attempts + 1
            return {
                'ok': False,
                'provisioned': provisioned,
                'pin_provisioned': provisioned,
                'locked': False,
                'remaining_attempts': remaining(failures),
                'error': error,
            }

        if attempts >= self._PIN_MAX_ATTEMPTS:
            return {
                'ok': False,
                'provisioned': provisioned,
                'pin_provisioned': provisioned,
                'locked': True,
                'remaining_attempts': 0,
                'error': _("Too many wrong attempts. Ask your supervisor to "
                           "unlock this tablet."),
            }
        given = str(pin or '').strip()
        if not provisioned:
            # Nothing to check against, so nothing was verified. Deliberately
            # NOT ok=True: this route must never claim a check it did not
            # perform, or a future caller that gates a write on `ok` would
            # wave every unprovisioned plant through. Checked before the
            # empty-PIN case on purpose: "there is nothing to enter" is a
            # truer answer than "enter your PIN".
            return {
                'ok': False,
                'provisioned': provisioned,
                'pin_provisioned': provisioned,
                'locked': False,
                'remaining_attempts': remaining(attempts),
                'error': _("No PIN is set on any operator profile yet."),
            }
        if not given:
            # No secret was even attempted, so nothing was guessed: not
            # counted toward the lockout.
            return {
                'ok': False,
                'provisioned': provisioned,
                'pin_provisioned': provisioned,
                'locked': False,
                'remaining_attempts': remaining(attempts),
                'error': _("Enter your PIN."),
            }
        # compare_digest, not ==: a 4-6 digit PIN is short enough that a
        # timing difference is worth removing. Compared as bytes because
        # compare_digest rejects non-ASCII str. Odoo validates the stored
        # value as digits-only (hr.employee._verify_pin), so this cannot be
        # hit today, but a 500 on a future relaxation of that rule would be
        # a self-inflicted outage on the floor.
        wanted = given.encode('utf-8')
        matched = request.env['hr.employee']
        for emp in employees:
            if hmac.compare_digest(str(emp.pin).encode('utf-8'), wanted):
                matched = emp
                break
        if matched:
            request.session['fmes_pin_failures'] = 0
            request.session['fmes_active_employee_id'] = matched.id
            request.session['fmes_active_user_id'] = (
                matched.user_id.id or request.env.uid)
            return {
                'ok': True,
                'provisioned': True,
                'pin_provisioned': True,
                'locked': False,
                'remaining_attempts': self._PIN_MAX_ATTEMPTS,
                'error': None,
                'employee_id': matched.id,
                'employee_name': matched.name,
                'user_id': matched.user_id.id or False,
            }
        return refuse(_("That PIN is not right."))

    @http.route('/fmes/terminal/pin_status', type='json', auth='user')
    def pin_status(self, **kwargs):
        """Which employee the shared tablet is currently switched to."""
        emp_id = request.session.get('fmes_active_employee_id')
        if emp_id:
            emp = request.env['hr.employee'].sudo().browse(emp_id).exists()
            if emp and emp.active:
                return {
                    'ok': True,
                    'active': True,
                    'employee_id': emp.id,
                    'employee_name': emp.name,
                }
        return {
            'ok': True,
            'active': False,
            'employee_id': False,
            'employee_name': False,
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

        Attribution: when the tablet has a PIN-switched operator, the event is
        recorded against that operator — fmes_operator_id (the employee whose
        PIN is active) and fmes_reported_by (their user, when they have one),
        the same field the chatter uses to notify the reporter. The stamp is
        written via the session login + sudo because an operator cannot read
        hr.employee through the ORM; the event record rules still protect it
        the same way as before.
        """
        try:
            entry = self._entry_for_user(entry_id)
            operator = self._active_employee()
            event = request.env['mrp.workcenter.productivity'].create({
                'workcenter_id': entry.workcenter_id.id,
                'loss_id': int(loss_id),
                'fmes_entry_id': entry.id,
                'fmes_remarks': remarks or False,
                'date_start': fields.Datetime.now(),
            })
            if operator:
                reporter = operator.user_id or request.env.user
                event.sudo().write({
                    'fmes_operator_id': operator.id,
                    'fmes_reported_by': reporter.id,
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
