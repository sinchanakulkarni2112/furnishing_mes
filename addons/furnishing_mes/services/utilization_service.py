# -*- coding: utf-8 -*-
"""Machine utilisation, efficiency and bottleneck analysis.

Requirement 5 in full, and the utilisation half of Requirement 3.6. The
metric formulas themselves live in `fmes.utilization.report` (the SQL view
that does the sum-then-divide aggregation, per D0.7); this service is the
one place that turns those numbers into decisions — a rolling percentage on
the machine record, an under-utilised list, and a bottleneck ranking a Plant
Manager can apply with one click and still override by hand afterward.
"""

from datetime import timedelta

from odoo import api, fields, models

# A machine below this rolling utilisation is flagged under-utilised
# (assumption A30, docs/15-open-questions-and-assumptions.md — consistent
# with a typical baseline OEE). A module constant, not a hard-coded business
# rule buried in logic: change it here until Phase 11 exposes it as a
# tunable fmes.alert.rule threshold instead.
UNDER_UTILIZED_THRESHOLD_PCT = 60.0

# A machine at or above this rolling utilisation is suggested as a
# bottleneck: it has the least slack of any machine, which is the
# pragmatic, defensible reading of "constrains overall throughput" without
# a full theory-of-constraints model this project has no data to support
# yet (that would need routing-level flow analysis, not just per-machine
# load). Always adjustable by hand afterward — see _suggest_bottlenecks.
BOTTLENECK_THRESHOLD_PCT = 90.0

# How far back "rolling" looks, matching the window Odoo's own native
# mrp.workcenter.oee uses, so the two figures are directly comparable.
ROLLING_WINDOW_DAYS = 30


class FmesUtilizationService(models.AbstractModel):
    _name = 'fmes.utilization.service'
    _description = 'Machine Utilisation Service'

    # ==================================================================
    # Per-machine rolling figures
    # ==================================================================
    @api.model
    def _since(self, days):
        return fields.Date.context_today(self) - timedelta(days=days)

    @api.model
    def _rolling_stats(self, workcenter, days=ROLLING_WINDOW_DAYS):
        """The full breakdown for one machine over `days` — hours, output
        and efficiency, not just the headline percentage. Used for a
        single-machine detail view; `_rolling_utilization_pct` below is the
        batch-efficient version behind the list-wide computed field.
        """
        rows = self.env['fmes.utilization.report'].search([
            ('workcenter_id', '=', workcenter.id),
            ('date', '>=', self._since(days)),
        ])
        available = sum(rows.mapped('available_hours'))
        run = sum(rows.mapped('run_hours'))
        actual = sum(rows.mapped('actual_qty'))
        std = sum(rows.mapped('std_output_qty'))
        return {
            'available_hours': available,
            'run_hours': run,
            'planned_downtime_hours': sum(
                rows.mapped('planned_downtime_hours')),
            'unplanned_downtime_hours': sum(
                rows.mapped('unplanned_downtime_hours')),
            'utilization_pct': (run / available * 100.0) if available else 0.0,
            'actual_qty': actual,
            'std_output_qty': std,
            'efficiency_pct': (actual / std * 100.0) if std else 0.0,
        }

    @api.model
    def _rolling_utilization_pct(self, workcenters, days=ROLLING_WINDOW_DAYS):
        """Utilisation % per machine, in one query rather than N.

        Returns {workcenter: pct}. A machine with no rows in the window (a
        new machine, or one genuinely idle the whole period) comes back at
        0.0 rather than being omitted — a silent gap here would make the
        under-utilised list miss the very machines most worth flagging.
        """
        if not workcenters:
            return {}
        data = self.env['fmes.utilization.report']._read_group(
            [('workcenter_id', 'in', workcenters.ids),
             ('date', '>=', self._since(days))],
            groupby=['workcenter_id'],
            aggregates=['run_hours:sum', 'available_hours:sum'])
        totals = {
            workcenter: (run or 0.0, available or 0.0)
            for workcenter, run, available in data
        }
        result = {}
        for wc in workcenters:
            run, available = totals.get(wc, (0.0, 0.0))
            result[wc] = (run / available * 100.0) if available else 0.0
        return result

    # ==================================================================
    # Under-utilised machines (Requirement 5.4)
    # ==================================================================
    @api.model
    def _under_utilized_machines(self, workcenters=None,
                                 threshold_pct=UNDER_UTILIZED_THRESHOLD_PCT,
                                 days=ROLLING_WINDOW_DAYS):
        """Machines whose rolling utilisation sits below `threshold_pct`,
        worst-first — so "the three least-utilised machines" (the Phase 6
        exit criterion) is just this result's first three.
        """
        workcenters = workcenters or self.env['mrp.workcenter'].search(
            [('active', '=', True)])
        pct_by_wc = self._rolling_utilization_pct(workcenters, days=days)
        under = [(wc, pct) for wc, pct in pct_by_wc.items()
                if pct < threshold_pct]
        under.sort(key=lambda pair: pair[1])
        return under

    # ==================================================================
    # Bottleneck ranking and suggestion (Requirement 5.5)
    # ==================================================================
    @api.model
    def _rank_by_utilization(self, workcenters=None, days=ROLLING_WINDOW_DAYS):
        """Machines ranked by rolling utilisation, highest (least slack)
        first — the pragmatic bottleneck signal this service uses."""
        workcenters = workcenters or self.env['mrp.workcenter'].search(
            [('active', '=', True)])
        pct_by_wc = self._rolling_utilization_pct(workcenters, days=days)
        return sorted(pct_by_wc.items(), key=lambda pair: pair[1],
                     reverse=True)

    @api.model
    def _suggest_bottlenecks(self, workcenters=None,
                             threshold_pct=BOTTLENECK_THRESHOLD_PCT,
                             days=ROLLING_WINDOW_DAYS):
        """Set fmes_is_bottleneck from current rolling utilisation.

        A full, deterministic recompute: every machine in scope ends up
        exactly True or False by the same rule, not a partial update that
        could drift from what the data now says. Still just a starting
        point — a Plant Manager triggers this deliberately and can correct
        any specific machine by hand afterward, same as before.

        Returns (flagged, cleared) work center recordsets, so the calling
        action can report back what changed.
        """
        workcenters = workcenters or self.env['mrp.workcenter'].search(
            [('active', '=', True)])
        pct_by_wc = self._rolling_utilization_pct(workcenters, days=days)
        flagged = self.env['mrp.workcenter']
        cleared = self.env['mrp.workcenter']
        for wc, pct in pct_by_wc.items():
            is_bottleneck = pct >= threshold_pct
            if wc.fmes_is_bottleneck == is_bottleneck:
                continue
            wc.fmes_is_bottleneck = is_bottleneck
            if is_bottleneck:
                flagged |= wc
            else:
                cleared |= wc
        return flagged, cleared
