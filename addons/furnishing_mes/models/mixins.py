# -*- coding: utf-8 -*-
"""Reusable mixins for Furnishing MES.

`fmes.erp.sync.mixin` is the dormant integration seam for ERP 10.8.

The connector itself is deferred by customer decision (see
docs/09-erp-integration-roadmap.md). The fields are reserved now because
retrofitting external identity onto records that already exist in production
would be a manual data-matching exercise across every order, product and
partner. Reserving the columns up front costs one mixin and eliminates that
migration entirely.

Nothing in the application reads or writes these fields yet.
"""

from odoo import fields, models


class FmesErpSyncMixin(models.AbstractModel):
    """Fields identifying a record's counterpart in an external ERP.

    Mixed into the models that ERP 10.8 will own or exchange:
    ``res.partner``, ``product.template``, ``mrp.bom``, ``sale.order`` and
    ``mrp.production`` (wired up when the connector is built).
    """

    _name = 'fmes.erp.sync.mixin'
    _description = 'ERP Synchronisation Mixin'

    erp_external_id = fields.Char(
        string='ERP Reference',
        index=True,
        copy=False,
        help="Primary key of this record in the external ERP. Blank for "
             "records created directly in the MES.",
    )
    erp_source_system = fields.Char(
        string='ERP Source System',
        default='erp_10_8',
        copy=False,
        help="Identifies which external system owns this record, so more than "
             "one source can be supported later without ambiguity.",
    )
    erp_last_sync = fields.Datetime(
        string='Last Synchronised',
        readonly=True,
        copy=False,
    )
    erp_sync_state = fields.Selection(
        selection=[
            ('not_synced', 'Not Synced'),
            ('synced', 'Synced'),
            ('pending', 'Pending'),
            ('error', 'Error'),
        ],
        string='Sync Status',
        default='not_synced',
        required=True,
        copy=False,
        index=True,
    )
    erp_sync_message = fields.Text(
        string='Sync Message',
        readonly=True,
        copy=False,
        help="Last error or diagnostic returned by the ERP exchange.",
    )
