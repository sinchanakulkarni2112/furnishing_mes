# -*- coding: utf-8 -*-
"""Maintenance equipment — the other half of the machine bridge.

Odoo Community has no `mrp_maintenance`, so the link between a work center and
its maintenance equipment is implemented here (gap G3 in
docs/13-odoo-edition-constraints.md).

Native `mtbf`, `mttr`, `expected_mtbf`, `latest_failure_date` and
`estimated_next_failure` are reused as-is and never recomputed by us.
"""

from datetime import timedelta

from odoo import api, fields, models

from .mrp_workcenter import CRITICALITY

# Health score weights (Requirement 7.6, assumption A50 — docs/15). Each
# factor is independently capped so no single one can sink the whole score
# on its own; a machine with no failure history yet or no target set is not
# penalised for the MTBF factor at all (absence of bad data is not itself
# bad — the same reasoning behind Phase 4's has_target/D-style null handling).
MTBF_SHORTFALL_WEIGHT = 30.0
OVERDUE_PM_PENALTY_PER = 10.0
OVERDUE_PM_PENALTY_CAP = 30.0
BREAKDOWN_PENALTY_PER = 8.0
BREAKDOWN_PENALTY_CAP = 40.0
BREAKDOWN_WINDOW_DAYS = 90


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    workcenter_id = fields.Many2one(
        'mrp.workcenter', string='Machine', copy=False,
        ondelete='set null', index=True,
        help="The production work center this equipment represents. Kept in "
             "step with the machine's own Maintenance Equipment field.")
    fmes_criticality = fields.Selection(
        CRITICALITY, string='Criticality', default='medium', required=True,
        help="Drives maintenance priority and the severity of breakdown "
             "alerts. Defaults from the linked machine when there is one.")
    fmes_department_id = fields.Many2one(
        related='workcenter_id.department_id', store=True, readonly=True,
        string='Department')
    fmes_schedule_ids = fields.One2many(
        'fmes.maintenance.schedule', 'equipment_id', string='PM Schedules')
    fmes_health_score = fields.Float(
        compute='_compute_fmes_health_score', string='Health Score',
        aggregator=None,
        help="0-100 composite: MTBF against the expected target, currently "
             "overdue preventive schedules, and breakdown frequency in the "
             "last 90 days (Requirement 7.6, assumption A50). Not a native "
             "Odoo figure — MTBF/MTTR themselves are read as-is from "
             "Odoo's own compute, only combined here.")

    # ------------------------------------------------------------------
    # Health score (Requirement 7, deliverable 5)
    # ------------------------------------------------------------------
    @api.depends('mtbf', 'expected_mtbf', 'fmes_schedule_ids.next_due_date',
                 'fmes_schedule_ids.state', 'maintenance_ids.maintenance_type',
                 'maintenance_ids.request_date')
    def _compute_fmes_health_score(self):
        today = fields.Date.context_today(self)
        window_start = today - timedelta(days=BREAKDOWN_WINDOW_DAYS)
        for equipment in self:
            # sudo(): native maintenance.equipment carries its own record
            # rule restricting a plain employee to equipment they follow
            # (maintenance/security/maintenance.xml, equipment_rule_user) —
            # our own ACL already lets any internal user read this model at
            # all, and the score is a read-only 0-100 summary, not the
            # underlying request/schedule rows themselves, so it should not
            # depend on who happens to follow this specific record.
            record = equipment.sudo()
            score = 100.0
            if record.expected_mtbf and record.mtbf:
                shortfall = max(
                    0.0, 1.0 - (record.mtbf / record.expected_mtbf))
                score -= MTBF_SHORTFALL_WEIGHT * shortfall
            overdue = record.fmes_schedule_ids.filtered(
                lambda s: s.state == 'active' and s.next_due_date
                and s.next_due_date < today)
            score -= min(OVERDUE_PM_PENALTY_CAP,
                        OVERDUE_PM_PENALTY_PER * len(overdue))
            breakdowns = record.maintenance_ids.filtered(
                lambda r: r.maintenance_type == 'corrective'
                and r.request_date and r.request_date >= window_start)
            score -= min(BREAKDOWN_PENALTY_CAP,
                        BREAKDOWN_PENALTY_PER * len(breakdowns))
            equipment.fmes_health_score = max(0.0, score)

    # ------------------------------------------------------------------
    # The equipment <-> work center bridge
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered('workcenter_id')._fmes_sync_workcenter_link()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'workcenter_id' in vals and not self.env.context.get(
                'fmes_bridge_sync'):
            self._fmes_sync_workcenter_link()
        return res

    def _fmes_sync_workcenter_link(self):
        """Mirror workcenter_id onto mrp.workcenter.equipment_id."""
        workcenter_model = self.env['mrp.workcenter']
        for equipment in self:
            stale = workcenter_model.search(
                [('equipment_id', '=', equipment.id)]) - equipment.workcenter_id
            if stale:
                stale.with_context(fmes_bridge_sync=True).write(
                    {'equipment_id': False})
            workcenter = equipment.workcenter_id
            if workcenter and workcenter.equipment_id.id != equipment.id:
                workcenter.with_context(fmes_bridge_sync=True).write(
                    {'equipment_id': equipment.id})

    @api.onchange('workcenter_id')
    def _onchange_workcenter_id(self):
        for equipment in self:
            if equipment.workcenter_id:
                equipment.fmes_criticality = \
                    equipment.workcenter_id.fmes_criticality
