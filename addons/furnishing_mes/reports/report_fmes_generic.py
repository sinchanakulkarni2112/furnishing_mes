# -*- coding: utf-8 -*-
"""PDF report document provider — moved out of services/report_service.py,
which holds the data service (deliverable 12's own aggregation) and had no
reason to also hold the report-rendering class itself; this belongs next to
this module's other read-model/report classes.
"""

from odoo import api, models


class ReportFmesGeneric(models.AbstractModel):
    """`_get_report_values` provider for the one shared QWeb PDF template
    (`views/fmes_report_templates.xml`). Named `report.<report_name>` per
    Odoo's own convention (`ir_actions_report._get_rendering_context_model`)
    — this is how the report engine finds it automatically, with no
    explicit wiring beyond the name itself.

    Pre-computes each wizard's `get_report_data` result once, here, rather
    than calling the service from inside the QWeb template — keeps the
    template itself free of Python logic, and this is directly unit
    testable the same way `fmes.dashboard.service.get_dashboard_data` is.
    """
    _name = 'report.furnishing_mes.report_fmes_generic'
    _description = 'Furnishing MES Report Document'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['fmes.report.wizard'].browse(docids)
        report_data = {}
        for doc in docs:
            report_data[doc.id] = self.env['fmes.report.service'].get_report_data(
                doc.report_type, doc.date_from, doc.date_to,
                department_ids=doc.department_ids.ids or None,
                workcenter_ids=doc.workcenter_ids.ids or None,
                shift_id=doc.shift_id.id or None,
                product_id=doc.product_id.id or None,
                company=doc.company_id)
        return {
            'doc_ids': docids,
            'doc_model': 'fmes.report.wizard',
            'docs': docs,
            'report_data': report_data,
        }
