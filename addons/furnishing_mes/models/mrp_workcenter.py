# -*- coding: utf-8 -*-
"""Machine master.

Machines are Odoo work centers. This extension adds what a furnishing plant
needs on top: the customer's own machine code, the owning department
(Requirement 3.2), standard manpower, criticality, and the link to the
maintenance equipment record (Requirement 7.1).

That last one is the bridge Odoo Enterprise provides through `mrp_maintenance`,
which is not available in Community — see docs/13-odoo-edition-constraints.md,
gap G3. It is kept consistent in both directions here.
"""

from odoo import _, api, fields, models

CRITICALITY = [
    ('low', 'Low'),
    ('medium', 'Medium'),
    ('high', 'High'),
    ('critical', 'Critical'),
]


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    fmes_machine_code = fields.Char(
        string='Machine Code', index=True, copy=False, tracking=True,
        help="The plant's own code for this machine, as used on the shop "
             "floor and in the customer's existing sheets.")
    department_id = fields.Many2one(
        'hr.department', string='Department', index=True, tracking=True,
        help="Department this machine belongs to. Drives department-wise "
             "monitoring and the supervisor's access scope.")
    equipment_id = fields.Many2one(
        'maintenance.equipment', string='Maintenance Equipment',
        copy=False, ondelete='set null', tracking=True,
        help="The equipment record used for preventive and breakdown "
             "maintenance of this machine.")
    fmes_std_manpower = fields.Float(
        string='Standard Manpower', default=1.0, tracking=True,
        help="Operators normally required to run this machine. Used as the "
             "fallback when the capacity matrix does not state one.")
    fmes_is_bottleneck = fields.Boolean(
        string='Bottleneck', tracking=True,
        help="Marks a machine that constrains overall throughput. The "
             "planning engine sequences bottlenecks first.")
    fmes_criticality = fields.Selection(
        CRITICALITY, string='Criticality', default='medium', required=True,
        tracking=True,
        help="How badly production suffers when this machine stops. Drives "
             "maintenance priority and alert severity.")

    fmes_capacity_ids = fields.One2many(
        'fmes.capacity.matrix', 'workcenter_id', string='Capacity Rates')
    fmes_capacity_count = fields.Integer(
        compute='_compute_fmes_capacity_count', string='Capacity Rates Defined')

    _sql_constraints = [
        ('fmes_equipment_uniq',
         'unique(equipment_id)',
         'This maintenance equipment is already linked to another machine.'),
    ]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('fmes_capacity_ids')
    def _compute_fmes_capacity_count(self):
        counts = dict(self.env['fmes.capacity.matrix']._read_group(
            [('workcenter_id', 'in', self.ids)],
            groupby=['workcenter_id'],
            aggregates=['__count'])) if self.ids else {}
        for workcenter in self:
            workcenter.fmes_capacity_count = counts.get(workcenter, 0)

    # ------------------------------------------------------------------
    # The work center <-> equipment bridge
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered('equipment_id')._fmes_sync_equipment_link()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'equipment_id' in vals and not self.env.context.get(
                'fmes_bridge_sync'):
            self._fmes_sync_equipment_link()
        return res

    def _fmes_sync_equipment_link(self):
        """Mirror equipment_id onto maintenance.equipment.workcenter_id.

        The context flag stops the two models writing to each other forever.
        """
        equipment_model = self.env['maintenance.equipment']
        for workcenter in self:
            # Detach equipment that still points here but is no longer linked.
            stale = equipment_model.search(
                [('workcenter_id', '=', workcenter.id)]) - workcenter.equipment_id
            if stale:
                stale.with_context(fmes_bridge_sync=True).write(
                    {'workcenter_id': False})
            equipment = workcenter.equipment_id
            if equipment and equipment.workcenter_id.id != workcenter.id:
                equipment.with_context(fmes_bridge_sync=True).write(
                    {'workcenter_id': workcenter.id})

    # ------------------------------------------------------------------
    # Capacity helpers
    # ------------------------------------------------------------------
    def fmes_get_output_rate(self, product, date=None):
        """Effective hourly output of this machine for `product`.

        Returns 0.0 when the capacity matrix has no applicable row.
        """
        self.ensure_one()
        return self.env['fmes.capacity.matrix']._get_rate(
            self, product, date=date)

    def fmes_get_std_manpower(self, product=None, date=None):
        """Operators required, preferring the capacity row over the machine."""
        self.ensure_one()
        if product:
            row = self.env['fmes.capacity.matrix']._resolve(
                self, product, date=date)
            if row and row.std_manpower:
                return row.std_manpower
        return self.fmes_std_manpower

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_fmes_view_capacity(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Capacity Rates: %s', self.display_name),
            'res_model': 'fmes.capacity.matrix',
            'view_mode': 'list,form',
            'domain': [('workcenter_id', '=', self.id)],
            'context': {
                'default_workcenter_id': self.id,
                'default_company_id': self.company_id.id or self.env.company.id,
            },
        }
