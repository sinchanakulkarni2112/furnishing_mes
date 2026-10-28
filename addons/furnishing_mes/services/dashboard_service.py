# -*- coding: utf-8 -*-
"""Executive Dashboard data (Requirement 9, all ten metrics).

One RPC, one Python method per tile — the OWL dashboard (Phase 10) is a thin
renderer over what this service computes; every aggregation happens here, in
plain, testable Python, never in JavaScript. That is what makes deliverable 7
possible at all: a test can call the same report models this service reads
and assert its own manually-aggregated figure equals what the service
returns, the same discipline `test_planning.py` already applies to the
scheduling board's own `get_board_data`.

Every aggregation follows the project's sum-then-divide rule (D0.7): read the
raw sums from a report model via `_read_group`, then divide — never average
a report row's own already-computed percentage across several rows.

Each underlying source is fetched EXACTLY ONCE per request
(`_fetch_production_rows` / `_fetch_utilization_rows`, grouped at the finest
grain any tile needs), not once per tile. Hitting either five separate times
— one per tile that reads it — re-does the same expensive aggregation five
times over. Deliverable 6 (a 100k-row dataset rendering in under two seconds)
is what caught that: the first version, one independent query per tile, took
over six seconds at that scale.

Task 3 then removed the remaining cost on the PRODUCTION side. Reading
`fmes.production.report` (an `_auto = False` SQL view) re-ran its four-table
JOIN and GROUP BY over the whole entry table on every call — measured at
1.77s on a 100k-row dataset, and still ~0.5s for a nine-day window, because
the aggregate is computed over the full table before the date filter is
applied. `fmes.production.entry` already carries every figure the dashboard
needs as a stored, indexed column (`ok_qty` and the standards are
`store=True`), so `_fetch_production_rows` now aggregates the base table
directly, at the finest grain any production-side tile actually reads, and the
view is no longer on this path at all. Measured effect on the 100k dataset:
1.77s -> 0.47s, with every figure bit-for-bit identical. The dashboard's own
`_kpis` arithmetic is untouched: same sums, same divisors, same order.

Because reading the base model means the ORM no longer applies
`fmes.production.report`'s record rule, `_department_scope_domain` applies
the caller's department scope explicitly — see its docstring.

`fmes.utilization.report` is still a SQL view and is still read directly
by `_fetch_utilization_rows`. It is now the largest single cost on a
100k-row dataset (2.11s for a full-span window), because it FULL OUTER JOINs
the entry table against the downtime-event table and so cannot be replaced by
one `_read_group` the way the production path could. That keeps a full-span
Executive Dashboard render above deliverable 6's two-second budget; see
docs/17-handover-checklist.md L1.
"""

from datetime import timedelta

from odoo import _, api, fields, models

# Assumption A28 (docs/15).
OEE_TARGET_PCT = 75.0
# Assumption A29.
ACHIEVEMENT_TARGET_PCT = 95.0
# Assumption A54.
UTILIZATION_TARGET_PCT = 85.0
DOWNTIME_TARGET_PCT = 10.0
# Assumption A30 — machine utilisation service's own under-utilised floor,
# reused here so the dashboard's ranking tile and the machine kanban badge
# never disagree about which machines are flagged.
UNDER_UTILIZED_THRESHOLD_PCT = 60.0
# Days-ahead window for "PMs due" on the KPI row, matching the maintenance-
# due alert cadence (assumption A33).
PM_DUE_LOOKAHEAD_DAYS = 7
# Ageing buckets for the backlog tile (docs/06-build-plan.md Phase 9
# deliverable 6), as (label, low, high) with high=None meaning open-ended.
BACKLOG_AGE_BUCKETS = [
    ('0-3', 0, 3),
    ('4-7', 4, 7),
    ('8-15', 8, 15),
    ('15+', 16, None),
]


class FmesDashboardService(models.AbstractModel):
    _name = 'fmes.dashboard.service'
    _description = 'Executive Dashboard Data Service'

    # ==================================================================
    # Public API
    # ==================================================================
    @api.model
    def get_dashboard_data(self, date_from, date_to, department_ids=None,
                           company_id=None):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        company = (self.env['res.company'].browse(company_id)
                  if company_id else self.env.company)
        departments = self.env['hr.department'].browse(department_ids or [])
        span = (date_to - date_from).days + 1
        prev_to = date_from - timedelta(days=1)
        prev_from = prev_to - timedelta(days=span - 1)

        production_rows = self._fetch_production_rows(
            date_from, date_to, departments, company)
        utilization_rows = self._fetch_utilization_rows(
            date_from, date_to, departments, company)
        prev_production_rows = self._fetch_production_rows(
            prev_from, prev_to, departments, company)
        prev_utilization_rows = self._fetch_utilization_rows(
            prev_from, prev_to, departments, company)

        return {
            'date_from': str(date_from),
            'date_to': str(date_to),
            'kpis': self._kpis(
                production_rows, utilization_rows, prev_production_rows,
                prev_utilization_rows, departments, company),
            'production_trend': self._production_trend(production_rows),
            'downtime_pareto': self._downtime_pareto(
                date_from, date_to, departments, company),
            'department_performance': self._department_performance(
                production_rows),
            'shift_performance': self._shift_performance(
                production_rows, utilization_rows),
            'machine_utilization_ranking': self._machine_utilization_ranking(
                utilization_rows),
            'capacity_utilization': self._capacity_utilization(
                date_from, date_to, departments, company),
            'backlog_ageing': self._backlog_ageing(departments, company),
            'maintenance_performance': self._maintenance_performance(
                date_from, date_to, departments, company),
            'productivity_trend': self._productivity_trend(production_rows),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _domain(self, date_from, date_to, departments, company,
               date_field='date'):
        domain = [
            (date_field, '>=', date_from), (date_field, '<=', date_to),
            ('company_id', '=', company.id),
        ]
        if departments:
            domain.append(('department_id', 'in', departments.ids))
        return domain

    @api.model
    def _department_scope_domain(self):
        """The caller's own department scope, as a domain against
        `fmes.production.entry`'s stored, indexed `department_id`.

        This read used to target `fmes.production.report`, whose supervisor
        record rule scoped it to `fmes_department_ids` for free — reading the
        base model means the ORM applies *that* model's rule, not the report's,
        so the same scope is restated here rather than assumed.

        Two details of `fmes_production_report_supervisor_dept_rule` are
        reproduced deliberately:

        - The `department_id = False` arm. A supervisor with departments
          assigned still sees rows on machines belonging to no department;
          dropping that arm would silently hide unassigned work.
        - The manager exemption. Phase 1's role hierarchy is cumulative, so a
          Plant Manager holds the supervisor group transitively and
          `has_group` alone would restrict them. They are excluded first,
          matching the report's own manager rule (`[(1, '=', 1)]`), which
          Odoo ORs against the supervisor rule.

        A caller with no `fmes_department_ids` gets no department clause at
        all, matching the `else [(1, '=', 1)]` branch of the same rule.
        """
        user = self.env.user
        if user.has_group('furnishing_mes.group_fmes_manager'):
            return []
        if not user.has_group('furnishing_mes.group_fmes_supervisor'):
            return []
        departments = user.fmes_department_ids
        if not departments:
            return []
        return ['|',
                ('department_id', 'in', departments.ids),
                ('department_id', '=', False)]

    @api.model
    def _fetch_production_rows(self, date_from, date_to, departments,
                               company):
        """Approved `fmes.production.entry` rows, fetched once, grouped at
        date x department x shift. Every production-side tile aggregates
        further from this same list in plain Python: the trend tiles by date,
        department performance by department, shift performance by shift, and
        the KPI row over the whole range. Those three keys are therefore the
        exact intersection of what is needed, and nothing finer pays for
        itself — on the 100k-row dataset `scripts/seed_load.py` builds, each
        entry lands on its own date/shift/machine combination, so grouping at
        the machine grain yields 99,954 groups (1.01s) while this grain yields
        38,871 (0.47s) for byte-identical figures.

        The machine dimension is deliberately absent: nothing downstream reads
        `row['workcenter']` off a production row. (The machine ranking tile
        reads it off a *utilisation* row, which does keep that dimension.)

        Read from the base table rather than `fmes.production.report` (Task 3,
        module docstring): every column aggregated here is stored and indexed
        there, so this is one indexed aggregate instead of a view that rebuilds
        its whole JOIN tree per query. `state = 'approved'` reproduces the
        view's own WHERE, so an unapproved figure still cannot reach a tile,
        and `department_id` is the same stored `workcenter_id.department_id`
        the view joined to `mrp_workcenter` for.

        `manpower_hours` is the one column the view computed in SQL as
        `SUM(actual_manpower * COALESCE(sh.net_hours, 0))`. `shift_id` is in
        the groupby, so net hours is constant within a group and
        `SUM(manpower) * net_hours` is that same sum — only the multiply moves
        from SQL to Python. Its `COALESCE` and the view's LEFT JOIN both cover
        a missing shift, which the required `shift_id` forbids; the guard is
        kept so the figures stay identical if that ever stops being true.
        """
        domain = self._domain(date_from, date_to, departments, company)
        domain.append(('state', '=', 'approved'))
        domain += self._department_scope_domain()
        data = self.env['fmes.production.entry']._read_group(
            domain, groupby=['date:day', 'department_id', 'shift_id'],
            aggregates=['planned_qty:sum', 'actual_qty:sum', 'ok_qty:sum',
                       'actual_manpower:sum'])
        rows = []
        for (row_date, department, shift, planned, actual, ok,
             manpower) in data:
            net_hours = (shift.net_hours or 0.0) if shift else 0.0
            rows.append({
                'date': row_date,
                'shift': shift,
                'department': department,
                'planned_qty': planned or 0.0,
                'actual_qty': actual or 0.0,
                'ok_qty': ok or 0.0,
                'manpower_hours': (manpower or 0.0) * net_hours,
            })
        return rows

    @api.model
    def _fetch_utilization_rows(self, date_from, date_to, departments,
                                company):
        """`fmes.utilization.report`, fetched once, at its own native date x
        shift x machine grain — every utilisation-side tile aggregates
        further from this same list."""
        domain = self._domain(date_from, date_to, departments, company)
        data = self.env['fmes.utilization.report']._read_group(
            domain, groupby=['date:day', 'shift_id', 'workcenter_id'],
            aggregates=['run_hours:sum', 'available_hours:sum',
                       'unplanned_downtime_hours:sum',
                       'planned_downtime_hours:sum', 'std_output_qty:sum',
                       'actual_qty:sum', 'ok_qty:sum'])
        rows = []
        for (row_date, shift, workcenter, run_hours, available_hours,
             unplanned_dt, planned_dt, std_output, actual_qty, ok_qty) in data:
            rows.append({
                'date': row_date,
                'shift': shift,
                'workcenter': workcenter,
                'department': (
                    workcenter.department_id if workcenter
                    else self.env['hr.department']),
                'run_hours': run_hours or 0.0,
                'available_hours': available_hours or 0.0,
                'unplanned_downtime_hours': unplanned_dt or 0.0,
                'planned_downtime_hours': planned_dt or 0.0,
                'std_output_qty': std_output or 0.0,
                'actual_qty': actual_qty or 0.0,
                'ok_qty': ok_qty or 0.0,
            })
        return rows

    # ==================================================================
    # KPI row
    # ==================================================================
    @api.model
    def _kpis(self, production_rows, utilization_rows, prev_production_rows,
             prev_utilization_rows, departments, company):
        current = self._kpi_raw(
            production_rows, utilization_rows, departments, company)
        previous = self._kpi_raw(
            prev_production_rows, prev_utilization_rows, departments,
            company)
        return {
            'achievement_pct': self._kpi_tile(
                current['achievement_pct'], previous['achievement_pct'],
                ACHIEVEMENT_TARGET_PCT, higher_is_better=True),
            'utilization_pct': self._kpi_tile(
                current['utilization_pct'], previous['utilization_pct'],
                UTILIZATION_TARGET_PCT, higher_is_better=True),
            'downtime_pct': self._kpi_tile(
                current['downtime_pct'], previous['downtime_pct'],
                DOWNTIME_TARGET_PCT, higher_is_better=False),
            'oee_pct': self._kpi_tile(
                current['oee_pct'], previous['oee_pct'], OEE_TARGET_PCT,
                higher_is_better=True),
            'backlog_qty': self._kpi_tile(
                current['backlog_qty'], previous['backlog_qty'], None,
                higher_is_better=False),
            # Live, unlike every other figure in this dict: no previous
            # window and no target, hence _kpi_tile's None tolerance below.
            'incoming_demand_qty': self._kpi_tile(
                self._incoming_demand(company), None, None,
                higher_is_better=False),
            'pm_due_count': self._kpi_tile(
                current['pm_due_count'], previous['pm_due_count'], None,
                higher_is_better=False),
        }

    @api.model
    def _kpi_tile(self, value, previous, target, higher_is_better):
        return {
            'value': round(value, 1),
            'previous': round(previous, 1) if previous is not None else None,
            'target': target,
            'higher_is_better': higher_is_better,
        }

    @api.model
    def _kpi_raw(self, production_rows, utilization_rows, departments,
                company):
        planned_qty = sum(r['planned_qty'] for r in production_rows)
        actual_qty = sum(r['actual_qty'] for r in production_rows)
        achievement_pct = (
            actual_qty / planned_qty * 100.0 if planned_qty else 0.0)

        run_hours = sum(r['run_hours'] for r in utilization_rows)
        available_hours = sum(r['available_hours'] for r in utilization_rows)
        unplanned_dt = sum(
            r['unplanned_downtime_hours'] for r in utilization_rows)
        planned_dt = sum(
            r['planned_downtime_hours'] for r in utilization_rows)
        std_output = sum(r['std_output_qty'] for r in utilization_rows)
        util_actual_qty = sum(r['actual_qty'] for r in utilization_rows)
        ok_qty = sum(r['ok_qty'] for r in utilization_rows)

        utilization_pct = (
            run_hours / available_hours * 100.0 if available_hours else 0.0)
        downtime_pct = (
            (unplanned_dt + planned_dt) / available_hours * 100.0
            if available_hours else 0.0)
        availability = (
            (available_hours - unplanned_dt) / available_hours
            if available_hours else 0.0)
        performance = (
            util_actual_qty / std_output if std_output else 0.0)
        quality = (ok_qty / util_actual_qty if util_actual_qty else 0.0)
        oee_pct = (
            availability * performance * quality * 100.0
            if (available_hours and std_output and util_actual_qty) else 0.0)

        backlog_qty = self._latest_backlog_qty(departments, company)
        pm_due_count = self._pm_due_count(departments, company)

        return {
            'achievement_pct': achievement_pct,
            'utilization_pct': utilization_pct,
            'downtime_pct': downtime_pct,
            'oee_pct': oee_pct,
            'backlog_qty': backlog_qty,
            'pm_due_count': pm_due_count,
        }

    @api.model
    def _latest_backlog_qty(self, departments, company):
        Snapshot = self.env['fmes.backlog.snapshot']
        latest = Snapshot.search_read(
            [('company_id', '=', company.id)],
            ['snapshot_date'], order='snapshot_date desc', limit=1)
        if not latest:
            return 0.0
        domain = [
            ('snapshot_date', '=', latest[0]['snapshot_date']),
            ('company_id', '=', company.id),
        ]
        if departments:
            domain.append(('department_id', 'in', departments.ids))
        data = Snapshot._read_group(domain, aggregates=['pending_qty:sum'])
        return (data[0][0] or 0.0) if data else 0.0

    @api.model
    def _incoming_demand(self, company):
        """Open customer demand no manufacturing order covers yet.

        The backlog tile next door reads last night's snapshot — what
        production already owes. This one is the other side of the ledger:
        what CUSTOMERS have ordered that production has not started at all,
        computed live so an order placed through the portal at 14:00 is on
        the dashboard at 14:01 instead of waiting for the 23:30 snapshot
        cron.

        Line-for-line the same demand `_collect_sale_order_demand` hands
        the planner (same order state, same company, same `type !=
        'service'`, same covering-MO set — draft/confirmed/progress — and
        the same per-line `ordered − delivered > 0` rule), so this tile
        and a `demand_source='mo_and_so'` plan run never disagree about
        what is still open. The per-line cap cannot be expressed as a
        domain (Odoo domains cannot compare two fields to each other) or
        as an aggregate (an over-delivered line would cancel a different
        line's open qty), hence the Python loop over the search.

        sudo(): `sale.order.line` grants read only to Salesmen and the
        portal group (sale/security/ir.model.access.csv), so operators,
        supervisors and Plant Managers would otherwise hit AccessError the
        moment this tile rendered. What leaves here is one number: the
        domain pins `order_id.company_id` explicitly (sudo bypasses the
        record rules that would have pinned it for us), and no partner,
        order reference or price travels with the figure.

        No department clause, deliberately — and that IS the department
        rule, applied: these lines have no department, because no
        manufacturing order exists yet to name one, which is exactly the
        `department_id = False` arm `_department_scope_domain` documents
        as always-visible for a scoped supervisor. Unassigned work is
        still work, and the covered half of demand is already on the
        department-scoped backlog tiles.
        """
        covered = self.env['mrp.production'].sudo().search([
            ('company_id', '=', company.id),
            ('state', 'in', ('draft', 'confirmed', 'progress')),
        ]).mapped('product_id')
        domain = [
            ('order_id.state', '=', 'sale'),
            ('order_id.company_id', '=', company.id),
            ('product_id.type', '!=', 'service'),
        ]
        if covered:
            domain.append(('product_id', 'not in', covered.ids))
        lines = self.env['sale.order.line'].sudo().search(domain)
        return sum(max(line.product_uom_qty - line.qty_delivered, 0.0)
                   for line in lines)

    @api.model
    def _pm_due_count(self, departments, company):
        today = fields.Date.context_today(self)
        horizon = today + timedelta(days=PM_DUE_LOOKAHEAD_DAYS)
        domain = [
            ('state', '=', 'active'), ('next_due_date', '!=', False),
            ('next_due_date', '<=', horizon),
            ('company_id', '=', company.id),
        ]
        if departments:
            domain.append(
                ('workcenter_id.department_id', 'in', departments.ids))
        return self.env['fmes.maintenance.schedule'].search_count(domain)

    # ==================================================================
    # Production trend
    # ==================================================================
    @api.model
    def _production_trend(self, production_rows):
        by_date = {}
        for row in production_rows:
            bucket = by_date.setdefault(
                row['date'], {'planned_qty': 0.0, 'actual_qty': 0.0})
            bucket['planned_qty'] += row['planned_qty']
            bucket['actual_qty'] += row['actual_qty']
        return [
            {'date': str(row_date), **values}
            for row_date, values in sorted(by_date.items())
        ]

    # ==================================================================
    # Downtime Pareto
    # ==================================================================
    @api.model
    def _downtime_pareto(self, date_from, date_to, departments, company):
        domain = self._domain(date_from, date_to, departments, company)
        data = self.env['fmes.downtime.report']._read_group(
            domain, groupby=['loss_id'], aggregates=['downtime_hours:sum'])
        rows = sorted(
            ((loss, hours or 0.0) for loss, hours in data),
            key=lambda pair: pair[1], reverse=True)
        total = sum(hours for _loss, hours in rows) or 0.0
        pareto = []
        cumulative = 0.0
        for loss, hours in rows:
            cumulative += hours
            pareto.append({
                'reason': loss.name if loss else _('Unspecified'),
                'hours': hours,
                'cumulative_pct': (
                    cumulative / total * 100.0 if total else 0.0),
            })
        return pareto

    # ==================================================================
    # Department / shift performance
    # ==================================================================
    @api.model
    def _department_performance(self, production_rows):
        by_dept = {}
        for row in production_rows:
            bucket = by_dept.setdefault(
                row['department'], {'planned_qty': 0.0, 'actual_qty': 0.0})
            bucket['planned_qty'] += row['planned_qty']
            bucket['actual_qty'] += row['actual_qty']
        rows = []
        for department, values in by_dept.items():
            rows.append({
                'department': department.name if department
                else _('Unassigned'),
                'achievement_pct': (
                    values['actual_qty'] / values['planned_qty'] * 100.0
                    if values['planned_qty'] else 0.0),
            })
        return rows

    @api.model
    def _shift_performance(self, production_rows, utilization_rows):
        achievement_by_shift = {}
        for row in production_rows:
            bucket = achievement_by_shift.setdefault(
                row['shift'], {'planned_qty': 0.0, 'actual_qty': 0.0})
            bucket['planned_qty'] += row['planned_qty']
            bucket['actual_qty'] += row['actual_qty']

        utilization_by_shift = {}
        for row in utilization_rows:
            bucket = utilization_by_shift.setdefault(
                row['shift'], {'run_hours': 0.0, 'available_hours': 0.0})
            bucket['run_hours'] += row['run_hours']
            bucket['available_hours'] += row['available_hours']

        shifts = set(achievement_by_shift) | set(utilization_by_shift)
        rows = []
        for shift in shifts:
            achievement = achievement_by_shift.get(
                shift, {'planned_qty': 0.0, 'actual_qty': 0.0})
            utilization = utilization_by_shift.get(
                shift, {'run_hours': 0.0, 'available_hours': 0.0})
            rows.append({
                'shift': shift.name if shift else _('Unassigned'),
                'achievement_pct': (
                    achievement['actual_qty'] / achievement['planned_qty']
                    * 100.0 if achievement['planned_qty'] else 0.0),
                'utilization_pct': (
                    utilization['run_hours'] / utilization['available_hours']
                    * 100.0 if utilization['available_hours'] else 0.0),
            })
        return sorted(rows, key=lambda r: r['shift'])

    # ==================================================================
    # Machine utilisation ranking
    # ==================================================================
    @api.model
    def _machine_utilization_ranking(self, utilization_rows):
        by_machine = {}
        for row in utilization_rows:
            bucket = by_machine.setdefault(
                row['workcenter'],
                {'run_hours': 0.0, 'available_hours': 0.0})
            bucket['run_hours'] += row['run_hours']
            bucket['available_hours'] += row['available_hours']
        rows = []
        for machine, values in by_machine.items():
            pct = (
                values['run_hours'] / values['available_hours'] * 100.0
                if values['available_hours'] else 0.0)
            rows.append({
                'machine': machine.display_name if machine else '',
                'utilization_pct': pct,
                'is_under_utilized': pct < UNDER_UTILIZED_THRESHOLD_PCT,
            })
        return sorted(rows, key=lambda r: r['utilization_pct'], reverse=True)

    # ==================================================================
    # Capacity utilisation (planning-side, distinct from execution-side
    # utilisation above — docs/11 section 1's own note)
    # ==================================================================
    @api.model
    def _capacity_utilization(self, date_from, date_to, departments,
                              company):
        line_domain = [
            ('date', '>=', date_from), ('date', '<=', date_to),
            ('plan_id.state', 'in', ('released', 'in_progress', 'done')),
            ('company_id', '=', company.id),
            ('state', '!=', 'cancelled'),
        ]
        if departments:
            line_domain.append(('department_id', 'in', departments.ids))
        lines = self.env['fmes.production.plan.line'].search(line_domain)

        engine = self.env['fmes.planning.engine']
        capacity_cache = {}
        planned_by_dept = {}
        capacity_by_dept = {}
        slots_seen = set()
        for line in lines:
            department = line.department_id
            planned_by_dept[department] = (
                planned_by_dept.get(department, 0.0) + line.planned_hours)
            slot_key = (line.workcenter_id.id, line.shift_id.id, line.date)
            dept_slot_key = (department.id, slot_key)
            if dept_slot_key in slots_seen:
                continue
            slots_seen.add(dept_slot_key)
            if slot_key not in capacity_cache:
                capacity_cache[slot_key] = engine._slot_capacity_hours(
                    line.workcenter_id, line.shift_id, line.date)
            capacity_by_dept[department] = (
                capacity_by_dept.get(department, 0.0)
                + capacity_cache[slot_key])

        rows = []
        for department in set(planned_by_dept) | set(capacity_by_dept):
            planned = planned_by_dept.get(department, 0.0)
            capacity = capacity_by_dept.get(department, 0.0)
            rows.append({
                'department': department.name if department
                else _('Unassigned'),
                'planned_hours': planned,
                'capacity_hours': capacity,
                'utilization_pct': (
                    planned / capacity * 100.0 if capacity else 0.0),
            })
        return sorted(rows, key=lambda r: r['department'])

    # ==================================================================
    # Backlog ageing
    # ==================================================================
    @api.model
    def _backlog_ageing(self, departments, company):
        Snapshot = self.env['fmes.backlog.snapshot']
        latest = Snapshot.search_read(
            [('company_id', '=', company.id)],
            ['snapshot_date'], order='snapshot_date desc', limit=1)
        buckets = [{
            'bucket': label, 'pending_qty': 0.0,
        } for label, _lo, _hi in BACKLOG_AGE_BUCKETS]
        if not latest:
            return buckets

        domain = [
            ('snapshot_date', '=', latest[0]['snapshot_date']),
            ('company_id', '=', company.id),
            ('pending_qty', '>', 0),
        ]
        if departments:
            domain.append(('department_id', 'in', departments.ids))
        rows = self.env['fmes.backlog.snapshot'].search_read(
            domain, ['days_delayed', 'pending_qty'])
        for index, (_label, low, high) in enumerate(BACKLOG_AGE_BUCKETS):
            total = 0.0
            for row in rows:
                days = row['days_delayed']
                if days >= low and (high is None or days <= high):
                    total += row['pending_qty']
            buckets[index]['pending_qty'] = total
        return buckets

    # ==================================================================
    # Maintenance performance
    # ==================================================================
    @api.model
    def _maintenance_performance(self, date_from, date_to, departments,
                                 company):
        equipment_domain = [('company_id', '=', company.id)]
        if departments:
            equipment_domain.append(
                ('workcenter_id.department_id', 'in', departments.ids))
        equipment = self.env['maintenance.equipment'].search(
            equipment_domain)
        with_history = equipment.filtered(lambda e: e.mtbf)
        avg_mtbf = (
            sum(with_history.mapped('mtbf')) / len(with_history)
            if with_history else 0.0)
        with_mttr = equipment.filtered(lambda e: e.mttr)
        avg_mttr = (
            sum(with_mttr.mapped('mttr')) / len(with_mttr)
            if with_mttr else 0.0)

        report_domain = [
            ('month', '>=', date_from.replace(day=1)), ('month', '<=', date_to),
            ('company_id', '=', company.id), ('has_pm_due', '=', True),
        ]
        if departments:
            report_domain.append(('department_id', 'in', departments.ids))
        # pm_compliance_pct itself cannot be summed (D0.7); the underlying
        # due/on-time counts are not separately exposed, so weight each
        # row's own compliance % by its own pm_due_count instead of a
        # naive average across months/equipment.
        rows = self.env['fmes.maintenance.report'].search(report_domain)
        total_due = sum(rows.mapped('pm_due_count')) or 0
        weighted_on_time = sum(
            r.pm_due_count * r.pm_compliance_pct for r in rows)
        pm_compliance_pct = (
            weighted_on_time / total_due if total_due else 0.0)

        breakdown_domain = [
            ('maintenance_type', '=', 'corrective'), ('close_date', '=', False),
            ('archive', '=', False), ('company_id', '=', company.id),
        ]
        if departments:
            breakdown_domain.append(
                ('workcenter_id.department_id', 'in', departments.ids))
        open_breakdowns = self.env['maintenance.request'].search_count(
            breakdown_domain)

        return {
            'mtbf': round(avg_mtbf, 1),
            'mttr': round(avg_mttr, 1),
            'pm_compliance_pct': round(pm_compliance_pct, 1),
            'open_breakdowns': open_breakdowns,
        }

    # ==================================================================
    # Productivity trend
    # ==================================================================
    @api.model
    def _productivity_trend(self, production_rows):
        by_date = {}
        for row in production_rows:
            bucket = by_date.setdefault(
                row['date'], {'ok_qty': 0.0, 'manpower_hours': 0.0})
            bucket['ok_qty'] += row['ok_qty']
            bucket['manpower_hours'] += row['manpower_hours']
        rows = []
        for row_date, values in sorted(by_date.items()):
            rows.append({
                'date': str(row_date),
                'units_per_manpower_hour': (
                    values['ok_qty'] / values['manpower_hours']
                    if values['manpower_hours'] else 0.0),
            })
        return rows
