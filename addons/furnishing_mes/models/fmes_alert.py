# -*- coding: utf-8 -*-
"""A raised alert (Requirement 10).

Written by `fmes.alert.engine`, never by hand — the same "photograph, not a
live view" reasoning `fmes.backlog.snapshot` documents (Phase 9): once an
alert exists, its `measured_value`/`threshold_value`/`subject` must keep
reading the way they did at the moment it fired, even if the rule's own
threshold is retuned afterward or the underlying record changes.

Two fields beyond docs/03's own list, both technical necessities for
Requirement 10's own wording, not scope creep:

- `notified_on` — when the actual notification (activity/email/Discuss) was
  dispatched, separate from `triggered_on` (when the condition was detected).
  Needed to implement assumption A35: a critical alert notifies immediately,
  a non-critical one is created now but its notification queues to 08:00.
- `escalated` — a plain flag so the escalation cron (deliverable 7) touches
  an unacknowledged critical alert's Plant-Manager notification exactly
  once, not every time it runs.
"""

from odoo import _, api, fields, models

STATES = [
    ('new', 'New'),
    ('acknowledged', 'Acknowledged'),
    ('resolved', 'Resolved'),
    ('dismissed', 'Dismissed'),
]


class FmesAlert(models.Model):
    _name = 'fmes.alert'
    _description = 'Alert'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'triggered_on desc'
    _rec_name = 'subject'

    rule_id = fields.Many2one(
        'fmes.alert.rule', string='Rule', required=True, index=True,
        ondelete='cascade')
    alert_type = fields.Selection(
        related='rule_id.alert_type', store=True, readonly=True)
    triggered_on = fields.Datetime(
        required=True, index=True, default=fields.Datetime.now)
    severity = fields.Selection(
        [('info', 'Info'), ('warning', 'Warning'), ('critical', 'Critical')],
        required=True,
        help="Snapshot of the rule's own severity at the moment this fired "
             "— frozen, the same reasoning as measured_value/threshold_value "
             "below, so a later retune of the rule cannot rewrite history.")
    subject = fields.Char(required=True)
    body = fields.Html()

    res_model = fields.Char(string='Related Model', index=True)
    res_id = fields.Many2oneReference(
        string='Related Record', model_field='res_model', index=True)

    measured_value = fields.Float()
    threshold_value = fields.Float()

    state = fields.Selection(
        STATES, default='new', required=True, index=True, tracking=True)
    acknowledged_by = fields.Many2one('res.users', readonly=True, copy=False)
    acknowledged_on = fields.Datetime(readonly=True, copy=False)
    resolution_note = fields.Text()

    notified_on = fields.Datetime(readonly=True, copy=False)
    escalated = fields.Boolean(default=False, copy=False)

    company_id = fields.Many2one('res.company', index=True)

    # ------------------------------------------------------------------
    # Workflow (deliverable 6 — Alert Center actions)
    # ------------------------------------------------------------------
    def action_acknowledge(self):
        for alert in self:
            if alert.state != 'new':
                continue
            alert.write({
                'state': 'acknowledged',
                'acknowledged_by': self.env.user.id,
                'acknowledged_on': fields.Datetime.now(),
            })

    def action_resolve(self):
        self.write({'state': 'resolved'})

    def action_dismiss(self):
        self.write({'state': 'dismissed'})

    def action_open_record(self):
        self.ensure_one()
        if not (self.res_model and self.res_id):
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
        }

    @api.model
    def get_unread_count(self):
        """Read by the Alert Center systray icon."""
        return self.search_count([('state', '=', 'new')])
