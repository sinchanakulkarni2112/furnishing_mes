# -*- coding: utf-8 -*-
"""Alert rule engine (Requirement 10).

Two ways a rule gets evaluated:

- **Threshold rules** (`excess_downtime`, `target_not_achieved`,
  `maintenance_due`, `critical_backlog`, `delayed_order`) — checked by the
  `fmes_evaluate_alerts` cron every 15 minutes, reading whatever data each
  type's own phase already built (downtime events, production entries,
  maintenance schedules, the backlog snapshot). Nothing here recomputes a
  figure another phase already owns; it only compares one against a rule's
  threshold.
- **Event rules** (`machine_breakdown`, `material_shortage`, and a blocked
  order re-evaluating `critical_backlog` immediately) — fired by
  `base_automation` records the moment the underlying condition becomes
  true, via `_on_event`, so a breakdown does not wait up to fifteen minutes
  to be noticed.

`_raise_alert` is the one place cooldown and "no duplicate for an already-
open condition" are enforced (deliverable 8) — every evaluator, threshold or
event, funnels through it.
"""

from datetime import datetime, time, timedelta

from odoo import _, api, fields, models

# Assumption A35 (docs/15): critical alerts notify immediately regardless of
# hour; anything else queues until this hour. A plain UTC hour check, not
# company-timezone-aware — a deliberate simplification, not an oversight;
# per-company scheduling would need a real timezone field res.company does
# not carry natively.
NIGHT_QUEUE_HOUR = 8
# Assumption A55: how long a critical alert may sit unacknowledged before
# the Plant Manager is notified directly.
ESCALATION_WINDOW_MINUTES = 30


class FmesAlertEngine(models.AbstractModel):
    _name = 'fmes.alert.engine'
    _description = 'Alert Rule Engine'

    # ==================================================================
    # Cron entry point
    # ==================================================================
    @api.model
    def _cron_evaluate_alerts(self):
        self._evaluate_threshold_rules()
        self._dispatch_queued_notifications()
        self._escalate_overdue_critical_alerts()

    @api.model
    def _evaluate_threshold_rules(self):
        rules = self.env['fmes.alert.rule'].search([('active', '=', True)])
        for rule in rules:
            method = getattr(self, '_eval_%s' % rule.alert_type, None)
            if not method:
                continue
            for record, measured_value in method(rule):
                self._raise_alert(rule, record, measured_value)

    # ==================================================================
    # Event entry point (base_automation)
    # ==================================================================
    @api.model
    def _on_event(self, records, alert_type):
        rules = self.env['fmes.alert.rule'].search([
            ('active', '=', True), ('alert_type', '=', alert_type),
        ])
        for rule in rules:
            for record in records:
                if not rule._department_in_scope(self._department_for(record)):
                    continue
                if not rule._workcenter_in_scope(self._workcenter_for(record)):
                    continue
                self._raise_alert(rule, record, 1.0)

    @api.model
    def _department_for(self, record):
        if 'department_id' in record._fields and record.department_id:
            return record.department_id
        if 'workcenter_id' in record._fields and record.workcenter_id:
            return record.workcenter_id.department_id
        return self.env['hr.department']

    @api.model
    def _workcenter_for(self, record):
        if record._name == 'mrp.workcenter':
            return record
        if 'workcenter_id' in record._fields:
            return record.workcenter_id
        return self.env['mrp.workcenter']

    # ==================================================================
    # Threshold evaluators — each returns [(record, measured_value), ...]
    # for candidates the rule's own operator/threshold has already matched.
    # ==================================================================
    @api.model
    def _eval_excess_downtime(self, rule):
        """Assumption A31: seeded as two rules sharing this type — one
        `threshold_uom='hours'` (> 1.0h = 60 min unplanned in one shift),
        one `'percent'` (> 10% of that shift). Worst shift per machine
        today is the candidate value, so a machine is not alerted twice for
        the same underlying stoppage split across shift boundaries."""
        today = fields.Date.context_today(self)
        window_start = datetime.combine(today, time.min)
        window_end = window_start + timedelta(days=1)
        events = self.env['mrp.workcenter.productivity'].search([
            ('date_start', '>=', window_start),
            ('date_start', '<', window_end),
            ('date_end', '!=', False),
            ('loss_type', '!=', 'productive'),
            ('loss_id.fmes_is_planned', '=', False),
            ('company_id', '=', rule.company_id.id),
        ])
        minutes_by_slot = {}
        for event in events:
            key = (event.workcenter_id, event.fmes_shift_id)
            minutes_by_slot[key] = minutes_by_slot.get(key, 0.0) + event.duration

        worst_by_machine = {}
        for (machine, shift), minutes in minutes_by_slot.items():
            if rule.threshold_uom == 'hours':
                value = minutes / 60.0
            else:
                net_hours = shift.net_hours if shift else 0.0
                value = (minutes / 60.0) / net_hours * 100.0 if net_hours else 0.0
            if machine not in worst_by_machine or value > worst_by_machine[machine]:
                worst_by_machine[machine] = value

        candidates = []
        for machine, value in worst_by_machine.items():
            if not rule._workcenter_in_scope(machine):
                continue
            if not rule._department_in_scope(machine.department_id):
                continue
            if rule._compares(value):
                candidates.append((machine, value))
        return candidates

    @api.model
    def _eval_target_not_achieved(self, rule):
        """Assumption A29: today's own submitted-or-approved entries — real-
        time, not gated on approval the way a report is (matching the OEE
        precedent in downtime_report.py's own docstring). The worst
        achievement % for the day is the candidate per machine."""
        today = fields.Date.context_today(self)
        entries = self.env['fmes.production.entry'].search([
            ('date', '=', today), ('state', 'in', ('submitted', 'approved')),
            ('has_target', '=', True), ('company_id', '=', rule.company_id.id),
        ])
        worst_by_machine = {}
        for entry in entries:
            machine = entry.workcenter_id
            value = entry.achievement_pct
            if machine not in worst_by_machine or value < worst_by_machine[machine]:
                worst_by_machine[machine] = value

        candidates = []
        for machine, value in worst_by_machine.items():
            if not rule._workcenter_in_scope(machine):
                continue
            if not rule._department_in_scope(machine.department_id):
                continue
            if rule._compares(value):
                candidates.append((machine, value))
        return candidates

    @api.model
    def _eval_maintenance_due(self, rule):
        """Assumption A33: seeded as two rules sharing this type — a
        warning at `threshold=7, operator='lte'` (days until due), a
        critical at `threshold=0, operator='lte'` (already overdue)."""
        today = fields.Date.context_today(self)
        schedules = self.env['fmes.maintenance.schedule'].search([
            ('state', '=', 'active'), ('next_due_date', '!=', False),
            ('company_id', '=', rule.company_id.id),
        ])
        candidates = []
        for schedule in schedules:
            machine = schedule.workcenter_id
            if not rule._workcenter_in_scope(machine):
                continue
            if not rule._department_in_scope(
                    machine.department_id if machine else None):
                continue
            days_until_due = (schedule.next_due_date - today).days
            if rule._compares(days_until_due):
                candidates.append((schedule, days_until_due))
        return candidates

    @api.model
    def _eval_material_shortage(self, rule):
        # Event-based only (`_on_event`, fired from base_automation the
        # moment a material-shortage downtime event is logged).
        return []

    @api.model
    def _eval_machine_breakdown(self, rule):
        # Event-based only, same reasoning.
        return []

    @api.model
    def _eval_critical_backlog(self, rule):
        """Assumption A32: `is_critical` on the LATEST snapshot is already
        the whole condition (aged > 15 days in the backlog, or > 7 days
        past deadline) — seeded with `threshold=0, operator='gt'` against a
        trivial measured_value of 1, the same "the gate is the condition"
        pattern `machine_breakdown`/`material_shortage` use."""
        rows = self._latest_snapshot_rows(rule, is_critical=True)
        candidates = []
        for row in rows:
            subject = row.production_id or row.sale_order_id
            if not subject:
                continue
            if not rule._department_in_scope(row.department_id):
                continue
            if rule._compares(1.0):
                candidates.append((subject, 1.0))
        return candidates

    @api.model
    def _eval_delayed_order(self, rule):
        """Assumption A26: delayed = past date_deadline, no buffer. Unlike
        critical_backlog, the rule's own threshold is meaningful here — a
        plant may want a higher bar than "any" lateness."""
        rows = self._latest_snapshot_rows(rule, status='delayed')
        candidates = []
        for row in rows:
            subject = row.production_id or row.sale_order_id
            if not subject:
                continue
            if not rule._department_in_scope(row.department_id):
                continue
            if rule._compares(row.days_delayed):
                candidates.append((subject, row.days_delayed))
        return candidates

    @api.model
    def _latest_snapshot_rows(self, rule, **extra_domain):
        Snapshot = self.env['fmes.backlog.snapshot']
        latest = Snapshot.search_read(
            [('company_id', '=', rule.company_id.id)],
            ['snapshot_date'], order='snapshot_date desc', limit=1)
        if not latest:
            return Snapshot
        domain = [
            ('snapshot_date', '=', latest[0]['snapshot_date']),
            ('company_id', '=', rule.company_id.id),
        ]
        domain += [(key, '=', value) for key, value in extra_domain.items()]
        return Snapshot.search(domain)

    # ==================================================================
    # Raising, cooldown, dispatch
    # ==================================================================
    @api.model
    def _raise_alert(self, rule, record, measured_value):
        if self._has_open_or_recent_alert(rule, record):
            return self.env['fmes.alert']
        alert = self.env['fmes.alert'].create({
            'rule_id': rule.id,
            'severity': rule.severity,
            'subject': _(
                "%(rule)s: %(record)s",
                rule=rule.name, record=record.display_name),
            'body': _(
                "<p>%(rule)s triggered on %(record)s.</p>"
                "<p>Measured value: %(value).2f — threshold: %(threshold).2f"
                "</p>",
                rule=rule.name, record=record.display_name,
                value=measured_value, threshold=rule.threshold),
            'res_model': record._name,
            'res_id': record.id,
            'measured_value': measured_value,
            'threshold_value': rule.threshold,
            'company_id': rule.company_id.id,
        })
        if rule.severity == 'critical':
            self._dispatch(alert)
        return alert

    @api.model
    def _has_open_or_recent_alert(self, rule, record):
        since = fields.Datetime.now() - timedelta(minutes=rule.cooldown_minutes)
        return bool(self.env['fmes.alert'].search_count([
            ('rule_id', '=', rule.id),
            ('res_model', '=', record._name), ('res_id', '=', record.id),
            '|', ('state', 'in', ('new', 'acknowledged')),
                 ('triggered_on', '>=', since),
        ]))

    @api.model
    def _dispatch_queued_notifications(self):
        if fields.Datetime.now().hour < NIGHT_QUEUE_HOUR:
            return
        pending = self.env['fmes.alert'].search([('notified_on', '=', False)])
        for alert in pending:
            self._dispatch(alert)

    @api.model
    def _dispatch(self, alert):
        rule = alert.rule_id
        recipients = rule._resolve_recipients()
        if rule.notify_activity and recipients:
            for user in recipients:
                alert.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=alert.subject, note=alert.body, user_id=user.id)
        if rule.notify_discuss and recipients:
            alert.message_post(
                body=alert.body,
                partner_ids=recipients.mapped('partner_id').ids,
                subtype_xmlid='mail.mt_comment')
        if (rule.notify_email and rule.severity == 'critical'
                and rule.mail_template_id and recipients):
            rule.mail_template_id.send_mail(
                alert.id, force_send=True,
                email_values={
                    'recipient_ids': [
                        (6, 0, recipients.mapped('partner_id').ids)],
                })
        alert.notified_on = fields.Datetime.now()

    # ==================================================================
    # Escalation (deliverable 7)
    # ==================================================================
    @api.model
    def _escalate_overdue_critical_alerts(self):
        cutoff = fields.Datetime.now() - timedelta(
            minutes=ESCALATION_WINDOW_MINUTES)
        overdue = self.env['fmes.alert'].search([
            ('severity', '=', 'critical'), ('state', '=', 'new'),
            ('escalated', '=', False), ('triggered_on', '<=', cutoff),
        ])
        if not overdue:
            return
        manager_group = self.env.ref('furnishing_mes.group_fmes_manager')
        managers = self.env['res.users'].search([
            ('groups_id', '=', manager_group.id)])
        for alert in overdue:
            for manager in managers:
                alert.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=_("Escalated: %s", alert.subject),
                    note=_(
                        "Unacknowledged %(minutes)s minutes after it fired.",
                        minutes=ESCALATION_WINDOW_MINUTES),
                    user_id=manager.id)
            alert.message_post(body=_(
                "Escalated to the Plant Manager — unacknowledged "
                "%(minutes)s minutes after it fired.",
                minutes=ESCALATION_WINDOW_MINUTES))
            alert.escalated = True
