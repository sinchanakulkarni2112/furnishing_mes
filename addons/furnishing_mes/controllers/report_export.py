# -*- coding: utf-8 -*-
"""XLSX export of an on-demand report (Requirement 12, deliverable 2).

Mirrors `controllers/plan_export.py`'s own pattern exactly: an existence
check before an access check (so a deleted wizard and one the user cannot
read return the same 404, never confirming which), then a workbook streamed
straight back rather than saved to disk.

The wizard record IS the parameter object — `fmes.report.wizard.action_
generate` redirects the browser here with the wizard's own id rather than
re-encoding its filters into the URL, so this route and the PDF path read
from exactly the same stored fields.
"""

import io

from odoo import _, http
from odoo.exceptions import AccessError, UserError
from odoo.http import content_disposition, request

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - xlsxwriter ships with Odoo
    xlsxwriter = None


class FmesReportExport(http.Controller):

    @http.route('/fmes/report/xlsx/<int:wizard_id>', type='http', auth='user')
    def export_report_xlsx(self, wizard_id, **kwargs):
        if xlsxwriter is None:
            raise UserError(_("xlsxwriter is not available on this server."))

        wizard = request.env['fmes.report.wizard'].browse(wizard_id).exists()
        if not wizard:
            raise request.not_found()
        try:
            wizard.check_access('read')
        except AccessError:
            raise request.not_found()

        data = request.env['fmes.report.service'].get_report_data(
            wizard.report_type, wizard.date_from, wizard.date_to,
            department_ids=wizard.department_ids.ids or None,
            workcenter_ids=wizard.workcenter_ids.ids or None,
            shift_id=wizard.shift_id.id or None,
            product_id=wizard.product_id.id or None,
            company=wizard.company_id)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True,
                                                'default_date_format': 'yyyy-mm-dd'})
        request.env['fmes.report.service'].write_xlsx(workbook, data)
        workbook.close()

        content = output.getvalue()
        filename = '%s.xlsx' % (data['title'] or 'report').replace('/', '_')
        return request.make_response(content, headers=[
            ('Content-Type',
             'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Length', len(content)),
            ('Content-Disposition', content_disposition(filename)),
        ])
