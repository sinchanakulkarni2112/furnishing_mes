# -*- coding: utf-8 -*-
"""ERP 10.8 synchronisation audit trail (dormant integration seam).

Completes the seam docs/09-erp-integration-roadmap.md section 1 describes
as built in Phase 1 and left dormant — Phase 15's own readiness review
found this model and `services/integration/`'s abstract adapter had never
actually been created, only specified (`fmes.erp.sync.mixin`, in
`models/mixins.py`, WAS actually built back then). Closing that gap now
rather than leaving the roadmap document's own claim false at handover.

Nothing in the application writes to this model yet — `fmes.sync.service`
(docs/09 section 3, not built until the connector itself is authorised)
is the only intended writer. Field list per docs/03-data-model.md
section 10.2.
"""

from odoo import fields, models

DIRECTIONS = [('inbound', 'Inbound'), ('outbound', 'Outbound')]
STATES = [
    ('running', 'Running'),
    ('success', 'Success'),
    ('partial', 'Partial Success'),
    ('failed', 'Failed'),
]


class FmesSyncLog(models.Model):
    _name = 'fmes.sync.log'
    _description = 'ERP Synchronisation Log'
    _order = 'started_on desc'

    direction = fields.Selection(DIRECTIONS, required=True, index=True)
    entity = fields.Char(
        required=True, index=True,
        help="The synchronised entity, e.g. 'sale.order', 'item_master' — "
             "an ERP-side name for inbound batches, an Odoo model name for "
             "outbound ones (docs/09 section 2).")
    record_count = fields.Integer(default=0)
    success_count = fields.Integer(default=0)
    error_count = fields.Integer(default=0)
    started_on = fields.Datetime(required=True, default=fields.Datetime.now)
    finished_on = fields.Datetime()
    state = fields.Selection(
        STATES, default='running', required=True, index=True)
    payload_ref = fields.Char(
        help="Pointer to the raw batch payload (a file path or an "
             "external batch id) for troubleshooting a failed sync — "
             "never the payload itself, which may carry ERP-side data "
             "this log has no business storing permanently.")
    message = fields.Text(help="Error or diagnostic detail, if any.")
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)
