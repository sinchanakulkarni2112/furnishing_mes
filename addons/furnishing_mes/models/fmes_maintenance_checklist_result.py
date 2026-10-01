# -*- coding: utf-8 -*-
"""What a technician actually found, per checklist item, on one request.

A snapshot, not a live reference to the template: `name`, `is_mandatory` and
`expected_value` are copied from `fmes.maintenance.checklist.line` at the
moment the request is generated (`fmes.maintenance.schedule._create_request`).
If the template changes next month, every past request's own filled checklist
must keep reading exactly as it did on the day the work happened — the same
reasoning Phase 4/5 apply to an approved entry's own figures.
"""

from odoo import fields, models


class FmesMaintenanceChecklistResult(models.Model):
    _name = 'fmes.maintenance.checklist.result'
    _description = 'Filled Preventive Maintenance Checklist Item'
    _order = 'request_id, sequence, id'

    request_id = fields.Many2one(
        'maintenance.request', string='Maintenance Request', required=True,
        ondelete='cascade', index=True)
    checklist_line_id = fields.Many2one(
        'fmes.maintenance.checklist.line', string='Template Line',
        ondelete='set null',
        help="The template line this was copied from. Kept only for "
             "traceability — never read for the item's own text, which is "
             "the snapshot fields below.")
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    is_mandatory = fields.Boolean(default=True)
    expected_value = fields.Char()
    actual_value = fields.Char(
        help="What the technician actually found or set.")
    is_done = fields.Boolean(string='Checked')
