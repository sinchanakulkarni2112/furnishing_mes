# -*- coding: utf-8 -*-
"""Preventive maintenance checklist template.

One line = one thing a technician checks on a given schedule ("Belt tension",
"Lubricate bearings", ...). These are the template; what a technician actually
found on a given visit is `fmes.maintenance.checklist.result` — a snapshot
taken when the request is generated, so a later edit to the template never
rewrites what already happened on a past request.
"""

from odoo import fields, models


class FmesMaintenanceChecklistLine(models.Model):
    _name = 'fmes.maintenance.checklist.line'
    _description = 'Preventive Maintenance Checklist Line'
    _order = 'schedule_id, sequence, id'

    schedule_id = fields.Many2one(
        'fmes.maintenance.schedule', string='Schedule', required=True,
        ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    is_mandatory = fields.Boolean(
        default=True,
        help="Unchecked items are informational; mandatory ones are what a "
             "technician is expected to actually verify.")
    expected_value = fields.Char(
        help="What a normal reading looks like, if there is one — a "
             "tolerance, a setting, a simple yes/no. Free text: the plant's "
             "own checklists vary too much per machine type for a fixed "
             "field shape to fit all of them.")
