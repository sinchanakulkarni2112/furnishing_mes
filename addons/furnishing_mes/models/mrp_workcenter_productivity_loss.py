# -*- coding: utf-8 -*-
"""Downtime loss reasons.

Odoo already models loss reasons as `mrp.workcenter.productivity.loss`, with a
`loss_type` of availability / performance / quality / productive that
`mrp.workcenter._compute_oee()` depends on. We extend that model rather than
building a parallel one (ADR-001) — a separate downtime taxonomy would leave
native OEE permanently wrong.

This adds the plant's own reason category on top, so Requirement 6 can report
by the language the supervisors actually use.
"""

from odoo import api, fields, models

# The customer's observed loss reasons, plus changeover and a catch-all.
FMES_LOSS_CATEGORY = [
    ('maintenance', 'Maintenance'),
    ('power_failure', 'Power Failure'),
    ('material_shortage', 'Material Shortage'),
    ('material_handling', 'Material Handling Delay'),
    ('operator_absence', 'Operator Absence'),
    ('manpower_rescheduling', 'Manpower Rescheduling'),
    ('operator_inefficiency', 'Operator Inefficiency'),
    ('unscheduled_stoppage', 'Unscheduled Stoppage'),
    ('changeover', 'Changeover / Setup'),
    ('other', 'Other'),
]


class MrpWorkcenterProductivityLoss(models.Model):
    _inherit = 'mrp.workcenter.productivity.loss'

    fmes_category = fields.Selection(
        FMES_LOSS_CATEGORY, string='Loss Category', index=True,
        help="The plant's own classification of this stoppage, used for "
             "downtime reporting and Pareto analysis. Odoo's own "
             "'Effectiveness Category' is kept separate because OEE depends "
             "on it.")
    fmes_is_planned = fields.Boolean(
        string='Planned Stoppage',
        help="Planned stoppages such as scheduled maintenance or a known "
             "changeover are excluded from availability loss, so they do not "
             "unfairly depress OEE.")
    fmes_requires_maintenance = fields.Boolean(
        string='Raises Maintenance Request',
        help="When an operator logs this reason, a maintenance request is "
             "raised automatically against the machine's equipment.")
    fmes_alert_threshold_hours = fields.Float(
        string='Alert After (hours)', default=1.0,
        help="Cumulative downtime for this reason in one shift that should "
             "trigger an excess-downtime alert. Zero disables the alert.")

    # ------------------------------------------------------------------
    # Classification of Odoo's own loss reasons
    # ------------------------------------------------------------------
    @api.model
    def _fmes_apply_default_categories(self):
        """Classify the loss reasons that Odoo's `mrp` module ships.

        These cannot be classified declaratively. Odoo declares them inside a
        ``<data noupdate="1">`` block, which sets ``ir.model.data.noupdate`` on
        the records themselves — so any later ``<record>`` aimed at them is
        skipped silently, whatever our own data block says. Calling this from a
        ``<function>`` tag is the only reliable route, and it runs on install
        and on every upgrade.

        Only reasons that are still unclassified are touched, so a plant that
        re-classifies one keeps its change across upgrades.
        """
        defaults = {
            'mrp.block_reason0': {
                'fmes_category': 'material_shortage',
                'fmes_alert_threshold_hours': 1.0,
            },
            'mrp.block_reason1': {
                'fmes_category': 'maintenance',
                'fmes_requires_maintenance': True,
                'fmes_alert_threshold_hours': 0.5,
            },
            'mrp.block_reason2': {
                'fmes_category': 'changeover',
                'fmes_is_planned': True,
                'fmes_alert_threshold_hours': 2.0,
            },
            'mrp.block_reason4': {
                'fmes_category': 'operator_inefficiency',
                'fmes_alert_threshold_hours': 2.0,
            },
            'mrp.block_reason5': {'fmes_category': 'other'},
            'mrp.block_reason6': {'fmes_category': 'other'},
            # block_reason7 is "Fully Productive Time": not a loss, so it is
            # deliberately left uncategorised.
        }
        for xmlid, vals in defaults.items():
            reason = self.env.ref(xmlid, raise_if_not_found=False)
            if reason and not reason.fmes_category:
                reason.write(vals)
