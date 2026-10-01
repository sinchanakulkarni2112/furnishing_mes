# -*- coding: utf-8 -*-
"""Backlog history (Requirement 4).

Written by `fmes.backlog.service` from the nightly `fmes_backlog_snapshot`
cron; never edited by hand — the UI is read-only by design (see the ACL).
Every field below is a plain, PLAIN field, not an `@api.depends` compute:
`days_delayed`, `status` and the rest are calculated once, at the moment a
row is written, against that night's own `snapshot_date` — never recomputed
against "today" on a later read. A live compute here would corrupt every
past night's history the first time someone opened it after today moved on:
a two-week-old snapshot's own `days_delayed` must always read the way it did
that night, not drift upward every day it stays in the database.
"""

from odoo import fields, models

BLOCK_REASONS = [
    ('material', 'Material'),
    ('machine', 'Machine'),
    ('manpower', 'Manpower'),
    ('quality', 'Quality'),
    ('customer_hold', 'Customer Hold'),
    ('other', 'Other'),
]

STATUSES = [
    ('pending', 'Pending'),
    ('blocked', 'Blocked'),
    ('delayed', 'Delayed'),
    ('at_risk', 'At Risk'),
    ('completed', 'Completed'),
]


class FmesBacklogSnapshot(models.Model):
    _name = 'fmes.backlog.snapshot'
    _description = 'Backlog Snapshot'
    _order = 'snapshot_date desc, days_delayed desc'
    _rec_name = 'product_id'

    snapshot_date = fields.Date(required=True, index=True)
    production_id = fields.Many2one(
        'mrp.production', string='Manufacturing Order', index=True,
        ondelete='cascade')
    sale_order_id = fields.Many2one(
        'sale.order', string='Sale Order', index=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Customer')
    product_id = fields.Many2one(
        'product.product', string='Product', required=True)
    department_id = fields.Many2one('hr.department', index=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Machine')

    ordered_qty = fields.Float(digits='Product Unit of Measure')
    produced_qty = fields.Float(digits='Product Unit of Measure')
    pending_qty = fields.Float(digits='Product Unit of Measure')
    completion_pct = fields.Float(aggregator=None)

    date_deadline = fields.Date()
    days_delayed = fields.Integer(
        help="snapshot_date minus date_deadline, floored at 0 (assumption "
             "A26 — no internal buffer).")
    status = fields.Selection(STATUSES, required=True, index=True)
    block_reason = fields.Selection(BLOCK_REASONS)
    block_note = fields.Text()
    is_critical = fields.Boolean(
        help="Aged more than 15 days in the backlog, or more than 7 days "
             "past its own deadline (assumption A32).")

    company_id = fields.Many2one('res.company')

    _sql_constraints = [
        ('fmes_backlog_snapshot_production_uniq',
         'unique(snapshot_date, production_id)',
         'This manufacturing order already has a snapshot for this date.'),
    ]
