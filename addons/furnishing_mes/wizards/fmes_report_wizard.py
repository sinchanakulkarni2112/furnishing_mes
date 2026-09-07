# -*- coding: utf-8 -*-
"""On-demand report generation wizard (Requirement 12, deliverable 3).

The common parameter screen behind every "Reports" menu item: date range,
department, machine, shift, product, and PDF/XLSX. Every menu item opens
this SAME wizard with a different `default_report_type` in its action
context — the report_type field itself is a plain dropdown, so any report
is reachable from any entry point, not just its own menu shortcut.

`action_generate` is deliberately thin: it does not fetch or format any
data itself. PDF goes through the standard `report_action()` mechanism
(the QWeb template calls `fmes.report.service.get_report_data` itself, at
render time); XLSX goes through a URL to `controllers/report_export.py`.
Both read this wizard's own stored filter fields, so the two formats of
the same request can never disagree.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services.report_service import REPORT_TYPES


class FmesReportWizard(models.TransientModel):
    _name = 'fmes.report.wizard'
    _description = 'Generate Report'

    report_type = fields.Selection(
        REPORT_TYPES, required=True, default='daily_production')
    date_from = fields.Date(
        required=True, default=lambda self: fields.Date.context_today(self))
    date_to = fields.Date(
        required=True, default=lambda self: fields.Date.context_today(self))
    department_ids = fields.Many2many(
        'hr.department', string='Departments',
        help="Leave empty to include every department.")
    workcenter_ids = fields.Many2many(
        'mrp.workcenter', string='Machines',
        help="Leave empty to include every machine.")
    shift_id = fields.Many2one('fmes.shift', string='Shift')
    product_id = fields.Many2one('product.product', string='Product')
    format = fields.Selection(
        [('pdf', 'PDF'), ('xlsx', 'XLSX')], required=True, default='pdf')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)

    @api.onchange('date_from')
    def _onchange_date_from(self):
        for wizard in self:
            if wizard.date_from and (
                    not wizard.date_to or wizard.date_to < wizard.date_from):
                wizard.date_to = wizard.date_from

    def action_generate(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_("The start date must not be after the end date."))

        if self.format == 'xlsx':
            return {
                'type': 'ir.actions.act_url',
                'url': '/fmes/report/xlsx/%d' % self.id,
                'target': 'self',
            }
        # config=False: report_action()'s default redirects an admin whose
        # company has no external_report_layout_id set to a "configure your
        # document layout" onboarding wizard instead of the report itself —
        # a one-time nudge meant for a brand-new install, not something a
        # Plant Manager clicking Generate should ever hit.
        return (self.env.ref('furnishing_mes.action_report_fmes_generic')
               .report_action(self, config=False))
