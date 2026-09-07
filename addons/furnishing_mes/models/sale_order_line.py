# -*- coding: utf-8 -*-
"""Production progress on a sale order line (Phase 13, docs/06 deliverable 4).

A customer's portal order page shows what fraction of what they ordered
has actually been produced, without exposing the internal detail (which
machine, what it cost, how much downtime it took) that gets there — only
the same three figures a supervisor's own backlog view already treats as
customer-safe: produced quantity, progress %, and an expected date.

`mrp.production.sale_line_id` is native (`sale_mrp`, auto-installed
alongside `sale` + `mrp`) — the manufacturing orders a confirmed sale
order line's own demand turned into. Reused as-is, never recomputed by a
parallel field, the same "extend Odoo, don't build parallel" rule as
everywhere else in this module (ADR-001).
"""

from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    fmes_production_ids = fields.Many2many(
        'mrp.production', string='Manufacturing Orders',
        compute='_compute_fmes_production_progress')
    fmes_produced_qty = fields.Float(
        string='Produced Qty', compute='_compute_fmes_production_progress',
        digits='Product Unit of Measure')
    fmes_progress_pct = fields.Float(
        string='Production Progress %',
        compute='_compute_fmes_production_progress',
        help="Produced quantity over ordered quantity, across every "
             "manufacturing order this line's demand produced. 0 when no "
             "manufacturing order has been linked yet.")
    fmes_expected_date = fields.Date(
        string='Expected Completion',
        compute='_compute_fmes_production_progress',
        help="The latest scheduled finish date among this line's own "
             "manufacturing orders, falling back to the order's own "
             "commitment date when none exist yet.")

    @api.depends('product_uom_qty', 'order_id.commitment_date')
    def _compute_fmes_production_progress(self):
        productions_by_line = self.env['mrp.production']._read_group(
            [('sale_line_id', 'in', self.ids)],
            groupby=['sale_line_id'], aggregates=['id:recordset'])
        productions_map = dict(productions_by_line)
        for line in self:
            productions = productions_map.get(line, self.env['mrp.production'])
            line.fmes_production_ids = productions
            line.fmes_produced_qty = sum(productions.mapped('qty_produced'))
            line.fmes_progress_pct = (
                line.fmes_produced_qty / line.product_uom_qty * 100.0
                if line.product_uom_qty else 0.0)
            finish_dates = [
                fields.Date.to_date(d)
                for d in productions.mapped('date_finished') if d]
            if finish_dates:
                line.fmes_expected_date = max(finish_dates)
            elif line.order_id.commitment_date:
                line.fmes_expected_date = fields.Date.to_date(
                    line.order_id.commitment_date)
            else:
                line.fmes_expected_date = False
