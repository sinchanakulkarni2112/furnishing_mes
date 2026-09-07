# -*- coding: utf-8 -*-
"""Alert rule configuration (Requirement 10).

One rule engine (`fmes.alert.engine`), one model for every threshold — a
Plant Manager tunes a number here rather than a developer changing code. The
seven alert types are the ones named in the customer requirement; nothing
about the model itself is type-specific, so an eighth type is a new
`ALERT_TYPES` entry and a matching `fmes.alert.engine._eval_<type>` method,
not a new model.

Two rules of the same type are how an "or" condition (assumption A31's
excess-downtime rule, A33's due-soon-or-overdue maintenance rule) is
expressed — the engine evaluates every active rule independently; nothing
stops two rules sharing a type with different thresholds and severities.
"""

from odoo import api, fields, models

ALERT_TYPES = [
    ('machine_breakdown', 'Machine Breakdown'),
    ('excess_downtime', 'Excess Downtime'),
    ('target_not_achieved', 'Target Not Achieved'),
    ('maintenance_due', 'Maintenance Due'),
    ('material_shortage', 'Material Shortage'),
    ('critical_backlog', 'Critical Backlog'),
    ('delayed_order', 'Delayed Order'),
]

SCOPES = [
    ('global', 'Global'),
    ('department', 'Department'),
    ('workcenter', 'Machine'),
]

OPERATORS = [
    ('gt', '>'),
    ('gte', '>='),
    ('lt', '<'),
    ('lte', '<='),
    ('eq', '='),
]

THRESHOLD_UOMS = [
    ('percent', '%'),
    ('hours', 'Hours'),
    ('qty', 'Qty'),
    ('days', 'Days'),
]

SEVERITIES = [
    ('info', 'Info'),
    ('warning', 'Warning'),
    ('critical', 'Critical'),
]

# Assumption A45 (docs/15) — one hour, so one stuck machine cannot generate a
# hundred alerts.
DEFAULT_COOLDOWN_MINUTES = 60


class FmesAlertRule(models.Model):
    _name = 'fmes.alert.rule'
    _description = 'Alert Rule'
    _order = 'alert_type, severity desc, name'

    name = fields.Char(required=True)
    alert_type = fields.Selection(ALERT_TYPES, required=True, index=True)
    scope = fields.Selection(SCOPES, default='global', required=True)
    department_ids = fields.Many2many(
        'hr.department', string='Departments',
        help="Leave empty, with scope Department, to apply to every "
             "department.")
    workcenter_ids = fields.Many2many(
        'mrp.workcenter', string='Machines',
        help="Leave empty, with scope Machine, to apply to every machine.")

    operator = fields.Selection(OPERATORS, default='gt', required=True)
    threshold = fields.Float(required=True)
    threshold_uom = fields.Selection(THRESHOLD_UOMS, default='percent')
    severity = fields.Selection(
        SEVERITIES, default='warning', required=True)

    recipient_group_ids = fields.Many2many(
        'res.groups', 'fmes_alert_rule_group_rel', string='Recipient Groups')
    recipient_user_ids = fields.Many2many(
        'res.users', 'fmes_alert_rule_user_rel', string='Recipient Users')

    notify_activity = fields.Boolean(default=True, string='In-App Activity')
    notify_email = fields.Boolean(
        default=False, string='Email',
        help="Fires only for critical-severity alerts regardless of this "
             "flag (assumption A34) — email is reserved for what genuinely "
             "needs it, to avoid the alert fatigue that gets alert systems "
             "switched off.")
    notify_discuss = fields.Boolean(default=True, string='Discuss Message')
    mail_template_id = fields.Many2one('mail.template', string='Email Template')

    cooldown_minutes = fields.Integer(
        default=DEFAULT_COOLDOWN_MINUTES, required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('fmes_alert_rule_cooldown_positive',
         'CHECK(cooldown_minutes > 0)',
         'Cooldown must be a positive number of minutes.'),
    ]

    # ------------------------------------------------------------------
    # Evaluation helpers
    # ------------------------------------------------------------------
    def _resolve_recipients(self):
        """Users this rule notifies: directly named users, plus every
        member of any named group. A `res.users` recordset, deduplicated."""
        self.ensure_one()
        users = self.recipient_user_ids
        for group in self.recipient_group_ids:
            users |= group.users
        return users

    def _compares(self, value):
        self.ensure_one()
        if self.operator == 'gt':
            return value > self.threshold
        if self.operator == 'gte':
            return value >= self.threshold
        if self.operator == 'lt':
            return value < self.threshold
        if self.operator == 'lte':
            return value <= self.threshold
        return value == self.threshold

    def _department_in_scope(self, department):
        self.ensure_one()
        if self.scope != 'department':
            return True
        if not self.department_ids:
            return True
        return bool(department) and department in self.department_ids

    def _workcenter_in_scope(self, workcenter):
        self.ensure_one()
        if self.scope != 'workcenter':
            return True
        if not self.workcenter_ids:
            return True
        return bool(workcenter) and workcenter in self.workcenter_ids
