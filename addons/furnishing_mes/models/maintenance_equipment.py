# -*- coding: utf-8 -*-
"""Maintenance equipment — the other half of the machine bridge.

Odoo Community has no `mrp_maintenance`, so the link between a work center and
its maintenance equipment is implemented here (gap G3 in
docs/13-odoo-edition-constraints.md).

Native `mtbf`, `mttr`, `expected_mtbf`, `latest_failure_date` and
`estimated_next_failure` are reused as-is and never recomputed by us.
"""

from odoo import api, fields, models

from .mrp_workcenter import CRITICALITY


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
