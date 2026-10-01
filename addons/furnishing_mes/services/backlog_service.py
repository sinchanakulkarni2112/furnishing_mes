# -*- coding: utf-8 -*-
"""Backlog classification and snapshotting (Requirement 4).

`fmes.backlog.snapshot` is a photograph, not a live view — every derived
figure here (pending qty, completion %, days delayed, status, criticality)
is computed ONCE, imperatively, at the moment a night's row is written, and
stored as a plain field. See the model's own docstring for why: a live
`@api.depends` compute would silently rewrite history every time "today"
moves on.

Two independent sources of backlog, matching the two demand sources the
planning engine itself already recognises (Phase 3):

- Every open `mrp.production` (has a routing, may already be scheduled).
- Confirmed `sale.order.line`s with no covering manufacturing order yet —
  committed demand the plant has not started production against. The
  "covering" check is the same one `_collect_sale_order_demand` uses, so a
  demand never counts twice across the two engines that read it.
"""

from odoo import api, fields, models

# Assumption A32 (docs/15): critical = aged more than 15 days in the
# backlog itself, OR more than 7 days past its own deadline — two distinct
# measures, not one restated twice. "Aged in the backlog" is only tracked
# for production-order-backed rows, which carry a stable production_id to
# look up prior nights by; a sale-order-line row with no production_id yet
# has no reliable history key, so its criticality is judged on lateness alone.
CRITICAL_AGE_DAYS = 15
CRITICAL_OVERDUE_DAYS = 7
# Assumption A53 (docs/15): not yet late, but due soon enough to flag before
# it becomes a problem rather than after.
AT_RISK_LOOKAHEAD_DAYS = 3


class FmesBacklogService(models.AbstractModel):
    _name = 'fmes.backlog.service'
    _description = 'Backlog Snapshot Service'

    # ==================================================================
    # Cron entry point
    # ==================================================================
    @api.model
    def _cron_write_snapshot(self):
        today = fields.Date.context_today(self)
        for company in self.env['res.company'].search([]):
            self._write_snapshot_for_company(today, company)

    @api.model
    def _write_snapshot_for_company(self, snapshot_date, company):
        """Idempotent: a re-run for the same date always converges to the
        same result, by wiping that date's own rows first rather than
        skipping or duplicating."""
        Snapshot = self.env['fmes.backlog.snapshot'].sudo()
        Snapshot.search([
            ('snapshot_date', '=', snapshot_date),
            ('company_id', '=', company.id),
        ]).unlink()

        productions = self.env['mrp.production'].search([
            ('company_id', '=', company.id),
            ('state', 'in', ('draft', 'confirmed', 'progress', 'to_close')),
        ])
        first_seen = self._first_seen_dates(productions)
        vals_list = [
            self._production_vals(
                production, snapshot_date,
                first_seen.get(production.id, snapshot_date))
            for production in productions
        ]

        covered_products = productions.mapped('product_id')
        order_lines = self.env['sale.order.line'].search([
            ('order_id.state', '=', 'sale'),
            ('order_id.company_id', '=', company.id),
            ('product_id.type', '!=', 'service'),
        ])
        for line in order_lines:
            if line.product_id in covered_products:
                continue
            if (line.product_uom_qty - line.qty_delivered) <= 0:
                continue
            vals_list.append(self._sale_line_vals(line, snapshot_date))

        if vals_list:
            Snapshot.create(vals_list)

    # ==================================================================
    # Row builders
    # ==================================================================
    @api.model
    def _first_seen_dates(self, productions):
        """Earliest snapshot_date each order has appeared under. An order
        with no prior history is first-seen tonight, by definition — it is
        not in this map, and callers default to snapshot_date themselves."""
        if not productions:
            return {}
        data = self.env['fmes.backlog.snapshot'].sudo()._read_group(
            [('production_id', 'in', productions.ids)],
            groupby=['production_id'], aggregates=['snapshot_date:min'])
        return {production.id: earliest for production, earliest in data}

    @api.model
    def _responsible_workcenter(self, production):
        """The machine whose department is currently on the hook to finish
        this order — its next not-yet-done operation, same ordering
        `_demands_for_production` uses. Empty when there is no routing."""
        workorders = production.workorder_ids.filtered(
            lambda w: w.state not in ('done', 'cancel'))
        if not workorders:
            return self.env['mrp.workcenter']
        next_workorder = workorders.sorted(
            lambda w: (w.operation_id.sequence or 0, w.id))[0]
        return next_workorder.workcenter_id

    @api.model
    def _classify(self, ordered_qty, produced_qty, date_deadline,
                 snapshot_date, is_blocked):
        pending_qty = max(ordered_qty - produced_qty, 0.0)
        completion_pct = (
            produced_qty / ordered_qty * 100.0 if ordered_qty else 0.0)
        days_delayed = 0
        if date_deadline and date_deadline < snapshot_date:
            days_delayed = (snapshot_date - date_deadline).days

        if pending_qty <= 0:
            status = 'completed'
        elif is_blocked:
            status = 'blocked'
        elif days_delayed > 0:
            status = 'delayed'
        elif date_deadline and (
                date_deadline - snapshot_date).days <= AT_RISK_LOOKAHEAD_DAYS:
            status = 'at_risk'
        else:
            status = 'pending'
        return pending_qty, completion_pct, days_delayed, status

    @api.model
    def _production_vals(self, production, snapshot_date, first_seen_date):
        ordered_qty = production.product_qty
        produced_qty = production.qty_produced
        date_deadline = (
            fields.Date.to_date(production.date_deadline)
            if production.date_deadline else False)
        workcenter = self._responsible_workcenter(production)
        pending_qty, completion_pct, days_delayed, status = self._classify(
            ordered_qty, produced_qty, date_deadline, snapshot_date,
            production.fmes_is_blocked)
        backlog_age_days = (snapshot_date - first_seen_date).days
        is_critical = (backlog_age_days > CRITICAL_AGE_DAYS
                      or days_delayed > CRITICAL_OVERDUE_DAYS)
        return {
            'snapshot_date': snapshot_date,
            'production_id': production.id,
            'product_id': production.product_id.id,
            'department_id': workcenter.department_id.id
            if workcenter else False,
            'workcenter_id': workcenter.id if workcenter else False,
            'ordered_qty': ordered_qty,
            'produced_qty': produced_qty,
            'pending_qty': pending_qty,
            'completion_pct': completion_pct,
            'date_deadline': date_deadline,
            'days_delayed': days_delayed,
            'status': status,
            'block_reason': production.fmes_block_reason,
            'block_note': production.fmes_block_note,
            'is_critical': is_critical,
            'company_id': production.company_id.id,
        }

    @api.model
    def _sale_line_vals(self, line, snapshot_date):
        order = line.order_id
        ordered_qty = line.product_uom_qty
        produced_qty = line.qty_delivered
        date_deadline = (
            fields.Date.to_date(order.commitment_date)
            if order.commitment_date else False)
        pending_qty, completion_pct, days_delayed, status = self._classify(
            ordered_qty, produced_qty, date_deadline, snapshot_date, False)
        return {
            'snapshot_date': snapshot_date,
            'sale_order_id': order.id,
            'partner_id': order.partner_id.id,
            'product_id': line.product_id.id,
            'ordered_qty': ordered_qty,
            'produced_qty': produced_qty,
            'pending_qty': pending_qty,
            'completion_pct': completion_pct,
            'date_deadline': date_deadline,
            'days_delayed': days_delayed,
            'status': status,
            'is_critical': days_delayed > CRITICAL_OVERDUE_DAYS,
            'company_id': order.company_id.id,
        }
