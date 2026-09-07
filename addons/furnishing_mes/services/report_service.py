# -*- coding: utf-8 -*-
"""Report data service (Requirement 12, all ten reports).

One Python method per report type, all funnelled through a single, uniform
shape — `{title, period_label, filters_label, summary, columns, rows}` (plus
`sections` for the Monthly MIS composite) — so ONE QWeb template and ONE
XLSX writer serve every report rather than ten near-identical pairs. The
wizard, the XLSX controller and the scheduled-report cron all call
`get_report_data` the same way, so a PDF, an XLSX and a scheduled email of
the same report on the same parameters can never quietly disagree.

Every report reads one of the read models already built in earlier phases
(`fmes.production.report`, `fmes.utilization.report`, `fmes.downtime.report`,
`fmes.maintenance.report`, `fmes.manpower.impact.report`,
`fmes.backlog.snapshot`, `fmes.production.plan.line`) or `fmes.alert` — this
phase adds no new aggregation logic beyond what those models already
provide, only presentation. The same sum-then-divide discipline (D0.7) as
every earlier phase: read raw sums via `_read_group`, divide once, never
average an already-computed per-row percentage.
"""

from datetime import timedelta

from odoo import _, api, fields, models

from ..models.fmes_alert_rule import ALERT_TYPES

# The single source of truth for "which ten report types exist" — imported
# by fmes.report.wizard and fmes.report.schedule for their own `report_type`
# Selection fields, so the three can never drift out of step with each
# other (plain strings, not translated markers: built once at import time,
# before any user session exists to translate against, the same reasoning
# ALERT_TYPES in fmes_alert_rule.py already follows).
REPORT_TYPES = [
    ('daily_production', 'Daily Production Report'),
    ('machine_utilisation', 'Machine Utilisation Report'),
    ('production_output_summary', 'Production Output Summary'),
    ('downtime', 'Downtime Report'),
    ('backlog', 'Backlog Report'),
    ('carry_forward_order', 'Carry Forward Order Report'),
    ('maintenance', 'Maintenance Report'),
    ('productivity', 'Productivity Report'),
    ('exception', 'Exception Report'),
    ('monthly_mis', 'Monthly Management MIS'),
]
REPORT_TITLES = dict(REPORT_TYPES)

# The five threshold-breach alert types the Exception Report consolidates
# (docs/11 section 4, report 9). machine_breakdown and material_shortage are
# operational events, not threshold breaches, and are left out on purpose.
EXCEPTION_ALERT_TYPES = [
    'target_not_achieved', 'excess_downtime', 'maintenance_due',
    'critical_backlog', 'delayed_order',
]

# Report types folded into the Monthly MIS composite, in display order.
MIS_SECTION_TYPES = [
    'production_output_summary', 'machine_utilisation', 'downtime',
    'backlog', 'maintenance', 'productivity', 'exception',
]

TOP_N = 5


class FmesReportService(models.AbstractModel):
    _name = 'fmes.report.service'
    _description = 'Report Data Service'

    # ==================================================================
    # Public API
    # ==================================================================
    @api.model
    def get_report_data(self, report_type, date_from, date_to,
                        department_ids=None, workcenter_ids=None,
                        shift_id=None, product_id=None, company=None,
                        summary_only=False):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        company = company or self.env.company
        departments = self.env['hr.department'].browse(department_ids or [])
        workcenters = self.env['mrp.workcenter'].browse(workcenter_ids or [])
        shift = self.env['fmes.shift'].browse(shift_id) if shift_id else None
        product = (self.env['product.product'].browse(product_id)
                  if product_id else None)
        ctx = {
            'date_from': date_from, 'date_to': date_to,
            'departments': departments, 'workcenters': workcenters,
            'shift': shift, 'product': product, 'company': company,
            'summary_only': summary_only,
        }

        if report_type == 'monthly_mis':
            data = self._data_monthly_mis(ctx)
        else:
            method = getattr(self, '_data_%s' % report_type, None)
            if not method:
                raise ValueError(_("Unknown report type: %s", report_type))
            data = method(ctx)

        data.setdefault('report_type', report_type)
        data.setdefault('title', REPORT_TITLES.get(report_type, report_type))
        data.setdefault(
            'period_label', '%s to %s' % (date_from, date_to))
        data.setdefault('filters_label', self._filters_label(ctx))
        data.setdefault('generated_on', fields.Datetime.now())
        data.setdefault('company', company)
        data.setdefault('sections', None)
        return data

    @api.model
    def format_value(self, value, fmt):
        """The one place a figure becomes displayed text, used by the QWeb
        template — so a PDF and its own XLSX round the same figure the same
        way (docs/11 section 1: rounding happens at presentation, never in
        intermediate aggregation)."""
        if value in (None, False) and fmt not in ('text',):
            if fmt in ('pct', 'hours', 'qty'):
                return '—'
        if fmt == 'pct':
            return '%.1f%%' % (value or 0.0)
        if fmt == 'hours':
            return '%.2f' % (value or 0.0)
        if fmt == 'qty':
            return '%.2f' % (value or 0.0)
        if fmt == 'int':
            return '%d' % (value or 0)
        if fmt == 'date':
            return str(value) if value else ''
        return '' if value is None or value is False else str(value)

    # ==================================================================
    # Shared helpers
    # ==================================================================
    @api.model
    def _filters_label(self, ctx):
        parts = []
        if ctx['departments']:
            parts.append(_("Departments: %s") % ', '.join(
                ctx['departments'].mapped('name')))
        if ctx['workcenters']:
            parts.append(_("Machines: %s") % ', '.join(
                ctx['workcenters'].mapped('name')))
        if ctx['shift']:
            parts.append(_("Shift: %s") % ctx['shift'].name)
        if ctx['product']:
            parts.append(_("Product: %s") % ctx['product'].display_name)
        return '; '.join(parts) if parts else _("No additional filters")

    @api.model
    def _domain(self, ctx, date_field='date', dept_field='department_id',
               wc_field='workcenter_id', shift_field='shift_id',
               product_field='product_id'):
        domain = [
            (date_field, '>=', ctx['date_from']),
            (date_field, '<=', ctx['date_to']),
            ('company_id', '=', ctx['company'].id),
        ]
        if ctx['departments'] and dept_field:
            domain.append((dept_field, 'in', ctx['departments'].ids))
        if ctx['workcenters'] and wc_field:
            domain.append((wc_field, 'in', ctx['workcenters'].ids))
        if ctx['shift'] and shift_field:
            domain.append((shift_field, '=', ctx['shift'].id))
        if ctx['product'] and product_field:
            domain.append((product_field, '=', ctx['product'].id))
        return domain

    @api.model
    def _previous_period(self, date_from, date_to):
        span = (date_to - date_from).days + 1
        prev_to = date_from - timedelta(days=1)
        prev_from = prev_to - timedelta(days=span - 1)
        return prev_from, prev_to

    @api.model
    def _safe_div(self, numerator, denominator, scale=1.0):
        return (numerator / denominator * scale) if denominator else 0.0

    # ==================================================================
    # 1. Daily Production Report — Date > Shift > Machine, one row per
    #    product (the read model's own native grain).
    # ==================================================================
    @api.model
    def _data_daily_production(self, ctx):
        domain = self._domain(ctx)
        rows = self.env['fmes.production.report'].search_read(
            domain,
            ['date', 'shift_id', 'workcenter_id', 'product_id',
             'planned_qty', 'actual_qty', 'rejected_qty', 'achievement_pct',
             'has_planned_qty', 'run_hours', 'downtime_hours',
             'actual_manpower'],
            order='date, shift_id, workcenter_id')
        total_planned = sum(r['planned_qty'] for r in rows)
        total_actual = sum(r['actual_qty'] for r in rows)
        summary = [
            {'label': _("Total Planned"), 'value': total_planned, 'fmt': 'qty'},
            {'label': _("Total Actual"), 'value': total_actual, 'fmt': 'qty'},
            {'label': _("Achievement %"),
             'value': self._safe_div(total_actual, total_planned, 100.0),
             'fmt': 'pct'},
            {'label': _("Total Run Hours"),
             'value': sum(r['run_hours'] for r in rows), 'fmt': 'hours'},
            {'label': _("Total Downtime Hours"),
             'value': sum(r['downtime_hours'] for r in rows), 'fmt': 'hours'},
        ]
        columns = [
            {'key': 'date', 'label': _("Date"), 'fmt': 'date'},
            {'key': 'shift_id', 'label': _("Shift"), 'fmt': 'text'},
            {'key': 'workcenter_id', 'label': _("Machine"), 'fmt': 'text'},
            {'key': 'product_id', 'label': _("Product"), 'fmt': 'text'},
            {'key': 'planned_qty', 'label': _("Planned"), 'fmt': 'qty'},
            {'key': 'actual_qty', 'label': _("Actual"), 'fmt': 'qty'},
            {'key': 'rejected_qty', 'label': _("Rejected"), 'fmt': 'qty'},
            {'key': 'achievement_pct', 'label': _("Achievement %"), 'fmt': 'pct'},
            {'key': 'run_hours', 'label': _("Run Hrs"), 'fmt': 'hours'},
            {'key': 'downtime_hours', 'label': _("Downtime Hrs"), 'fmt': 'hours'},
            {'key': 'actual_manpower', 'label': _("Manpower"), 'fmt': 'qty'},
        ]
        table_rows = [{
            'date': r['date'],
            'shift_id': r['shift_id'][1] if r['shift_id'] else '',
            'workcenter_id': r['workcenter_id'][1] if r['workcenter_id'] else '',
            'product_id': r['product_id'][1] if r['product_id'] else '',
            'planned_qty': r['planned_qty'],
            'actual_qty': r['actual_qty'],
            'rejected_qty': r['rejected_qty'],
            'achievement_pct': r['achievement_pct'] if r['has_planned_qty'] else None,
            'run_hours': r['run_hours'],
            'downtime_hours': r['downtime_hours'],
            'actual_manpower': r['actual_manpower'],
        } for r in rows]
        return {'summary': summary, 'columns': columns, 'rows': table_rows}

    # ==================================================================
    # 2. Machine Utilisation Report — Machine > Date, native grain.
    # ==================================================================
    @api.model
    def _data_machine_utilisation(self, ctx):
        domain = self._domain(ctx, product_field=None)
        rows = self.env['fmes.utilization.report'].search_read(
            domain,
            ['date', 'shift_id', 'workcenter_id', 'available_hours',
             'run_hours', 'unplanned_downtime_hours',
             'planned_downtime_hours', 'idle_hours', 'utilization_pct',
             'availability', 'performance', 'quality', 'oee_pct'],
            order='workcenter_id, date')
        total_available = sum(r['available_hours'] for r in rows)
        total_run = sum(r['run_hours'] for r in rows)
        total_unplanned = sum(r['unplanned_downtime_hours'] for r in rows)
        summary = [
            {'label': _("Available Hours"), 'value': total_available, 'fmt': 'hours'},
            {'label': _("Run Hours"), 'value': total_run, 'fmt': 'hours'},
            {'label': _("Utilisation %"),
             'value': self._safe_div(total_run, total_available, 100.0),
             'fmt': 'pct'},
            {'label': _("Unplanned Downtime Hours"),
             'value': total_unplanned, 'fmt': 'hours'},
        ]
        columns = [
            {'key': 'workcenter_id', 'label': _("Machine"), 'fmt': 'text'},
            {'key': 'date', 'label': _("Date"), 'fmt': 'date'},
            {'key': 'available_hours', 'label': _("Available"), 'fmt': 'hours'},
            {'key': 'run_hours', 'label': _("Run"), 'fmt': 'hours'},
            {'key': 'unplanned_downtime_hours', 'label': _("Unplanned Down"), 'fmt': 'hours'},
            {'key': 'idle_hours', 'label': _("Idle"), 'fmt': 'hours'},
            {'key': 'utilization_pct', 'label': _("Utilisation %"), 'fmt': 'pct'},
            {'key': 'availability', 'label': _("Availability"), 'fmt': 'pct'},
            {'key': 'performance', 'label': _("Performance"), 'fmt': 'pct'},
            {'key': 'quality', 'label': _("Quality"), 'fmt': 'pct'},
            {'key': 'oee_pct', 'label': _("OEE %"), 'fmt': 'pct'},
        ]
        table_rows = [{
            'workcenter_id': r['workcenter_id'][1] if r['workcenter_id'] else '',
            'date': r['date'],
            'available_hours': r['available_hours'],
            'run_hours': r['run_hours'],
            'unplanned_downtime_hours': r['unplanned_downtime_hours'],
            'idle_hours': r['idle_hours'],
            'utilization_pct': r['utilization_pct'],
            'availability': (r['availability'] or 0.0) * 100.0,
            'performance': (r['performance'] or 0.0) * 100.0,
            'quality': (r['quality'] or 0.0) * 100.0,
            'oee_pct': r['oee_pct'],
        } for r in rows]
        return {'summary': summary, 'columns': columns, 'rows': table_rows}

    # ==================================================================
    # 3. Production Output Summary — Period > Department > Product,
    #    aggregated (sum-then-divide), with a trend vs the previous period.
    # ==================================================================
    @api.model
    def _data_production_output_summary(self, ctx):
        domain = self._domain(ctx)
        data = self.env['fmes.production.report']._read_group(
            domain, groupby=['department_id', 'product_id'],
            aggregates=['planned_qty:sum', 'actual_qty:sum',
                       'ok_qty:sum', 'rejected_qty:sum'])
        rows = []
        total_planned = total_actual = 0.0
        for department, product, planned, actual, ok, rejected in data:
            planned = planned or 0.0
            actual = actual or 0.0
            total_planned += planned
            total_actual += actual
            rows.append({
                'department_id': department.name or '',
                'product_id': product.display_name if product else '',
                'planned_qty': planned,
                'actual_qty': actual,
                'ok_qty': ok or 0.0,
                'rejected_qty': rejected or 0.0,
                'achievement_pct': self._safe_div(actual, planned, 100.0),
            })
        current_pct = self._safe_div(total_actual, total_planned, 100.0)

        prev_from, prev_to = self._previous_period(
            ctx['date_from'], ctx['date_to'])
        prev_ctx = dict(ctx, date_from=prev_from, date_to=prev_to)
        prev_domain = self._domain(prev_ctx)
        prev_data = self.env['fmes.production.report']._read_group(
            prev_domain, aggregates=['planned_qty:sum', 'actual_qty:sum'])
        prev_planned, prev_actual = prev_data[0] if prev_data else (0.0, 0.0)
        previous_pct = self._safe_div(
            prev_actual or 0.0, prev_planned or 0.0, 100.0)

        summary = [
            {'label': _("Total Planned"), 'value': total_planned, 'fmt': 'qty'},
            {'label': _("Total Actual"), 'value': total_actual, 'fmt': 'qty'},
            {'label': _("Achievement %"), 'value': current_pct, 'fmt': 'pct'},
            {'label': _("Achievement % (Previous Period)"),
             'value': previous_pct, 'fmt': 'pct'},
        ]
        columns = [
            {'key': 'department_id', 'label': _("Department"), 'fmt': 'text'},
            {'key': 'product_id', 'label': _("Product"), 'fmt': 'text'},
            {'key': 'planned_qty', 'label': _("Planned"), 'fmt': 'qty'},
            {'key': 'actual_qty', 'label': _("Actual"), 'fmt': 'qty'},
            {'key': 'ok_qty', 'label': _("Good"), 'fmt': 'qty'},
            {'key': 'rejected_qty', 'label': _("Rejected"), 'fmt': 'qty'},
            {'key': 'achievement_pct', 'label': _("Achievement %"), 'fmt': 'pct'},
        ]
        if ctx['summary_only']:
            rows = sorted(
                rows, key=lambda r: r['actual_qty'], reverse=True)[:TOP_N]
        return {'summary': summary, 'columns': columns, 'rows': rows}

    # ==================================================================
    # 4. Downtime Report — Category > Reason > Machine, aggregated, with
    #    a top-5 Pareto band.
    # ==================================================================
    @api.model
    def _data_downtime(self, ctx):
        domain = self._domain(ctx, product_field=None)
        data = self.env['fmes.downtime.report']._read_group(
            domain, groupby=['fmes_category', 'loss_id', 'workcenter_id'],
            aggregates=['downtime_hours:sum', 'event_count:sum'])
        rows = []
        total_hours = 0.0
        for category, loss, workcenter, hours, events in data:
            hours = hours or 0.0
            events = events or 0
            total_hours += hours
            rows.append({
                'fmes_category': category or '',
                'loss_id': loss.name if loss else '',
                'workcenter_id': workcenter.name if workcenter else '',
                'downtime_hours': hours,
                'event_count': events,
                'avg_event_duration': self._safe_div(hours, events),
            })
        rows.sort(key=lambda r: r['downtime_hours'], reverse=True)
        for row in rows:
            row['pct_of_total'] = self._safe_div(
                row['downtime_hours'], total_hours, 100.0)

        summary = [
            {'label': _("Total Downtime Hours"), 'value': total_hours, 'fmt': 'hours'},
            {'label': _("Total Events"),
             'value': sum(r['event_count'] for r in rows), 'fmt': 'int'},
            {'label': _("Top Reason"),
             'value': rows[0]['loss_id'] if rows else '—', 'fmt': 'text'},
        ]
        columns = [
            {'key': 'fmes_category', 'label': _("Category"), 'fmt': 'text'},
            {'key': 'loss_id', 'label': _("Reason"), 'fmt': 'text'},
            {'key': 'workcenter_id', 'label': _("Machine"), 'fmt': 'text'},
            {'key': 'downtime_hours', 'label': _("Hours"), 'fmt': 'hours'},
            {'key': 'event_count', 'label': _("Events"), 'fmt': 'int'},
            {'key': 'avg_event_duration', 'label': _("Avg (hrs)"), 'fmt': 'hours'},
            {'key': 'pct_of_total', 'label': _("% of Total"), 'fmt': 'pct'},
        ]
        if ctx['summary_only']:
            rows = rows[:TOP_N]
        return {'summary': summary, 'columns': columns, 'rows': rows}

    # ==================================================================
    # 5. Backlog Report — Status > Department > Order, as of date_to.
    # ==================================================================
    @api.model
    def _data_backlog(self, ctx):
        Snapshot = self.env['fmes.backlog.snapshot']
        latest = Snapshot.search_read(
            [('snapshot_date', '<=', ctx['date_to']),
             ('company_id', '=', ctx['company'].id)],
            ['snapshot_date'], order='snapshot_date desc', limit=1)
        rows, snapshot_date = [], None
        if latest:
            snapshot_date = latest[0]['snapshot_date']
            domain = [
                ('snapshot_date', '=', snapshot_date),
                ('company_id', '=', ctx['company'].id),
            ]
            if ctx['departments']:
                domain.append(('department_id', 'in', ctx['departments'].ids))
            if ctx['workcenters']:
                domain.append(('workcenter_id', 'in', ctx['workcenters'].ids))
            records = Snapshot.search_read(
                domain,
                ['status', 'department_id', 'production_id', 'sale_order_id',
                 'partner_id', 'product_id', 'ordered_qty', 'produced_qty',
                 'pending_qty', 'date_deadline', 'days_delayed',
                 'block_reason', 'is_critical'],
                order='status, department_id, days_delayed desc')
            for r in records:
                order = r['production_id'] or r['sale_order_id']
                rows.append({
                    'status': r['status'],
                    'department_id': r['department_id'][1] if r['department_id'] else '',
                    'order': order[1] if order else '',
                    'partner_id': r['partner_id'][1] if r['partner_id'] else '',
                    'product_id': r['product_id'][1] if r['product_id'] else '',
                    'ordered_qty': r['ordered_qty'],
                    'produced_qty': r['produced_qty'],
                    'pending_qty': r['pending_qty'],
                    'date_deadline': r['date_deadline'],
                    'days_delayed': r['days_delayed'],
                    'block_reason': r['block_reason'] or '',
                })
        total_pending = sum(r['pending_qty'] for r in rows)
        critical_count = len([r for r in rows if r['days_delayed'] and r['days_delayed'] > 15])
        summary = [
            {'label': _("As of"), 'value': snapshot_date, 'fmt': 'date'},
            {'label': _("Open Orders"), 'value': len(rows), 'fmt': 'int'},
            {'label': _("Total Pending Qty"), 'value': total_pending, 'fmt': 'qty'},
            {'label': _("Critical (>15 days)"), 'value': critical_count, 'fmt': 'int'},
        ]
        columns = [
            {'key': 'status', 'label': _("Status"), 'fmt': 'text'},
            {'key': 'department_id', 'label': _("Department"), 'fmt': 'text'},
            {'key': 'order', 'label': _("Order"), 'fmt': 'text'},
            {'key': 'partner_id', 'label': _("Customer"), 'fmt': 'text'},
            {'key': 'product_id', 'label': _("Product"), 'fmt': 'text'},
            {'key': 'ordered_qty', 'label': _("Ordered"), 'fmt': 'qty'},
            {'key': 'produced_qty', 'label': _("Produced"), 'fmt': 'qty'},
            {'key': 'pending_qty', 'label': _("Pending"), 'fmt': 'qty'},
            {'key': 'date_deadline', 'label': _("Deadline"), 'fmt': 'date'},
            {'key': 'days_delayed', 'label': _("Days Delayed"), 'fmt': 'int'},
            {'key': 'block_reason', 'label': _("Block Reason"), 'fmt': 'text'},
        ]
        if ctx['summary_only']:
            rows = sorted(
                rows, key=lambda r: r['days_delayed'] or 0,
                reverse=True)[:TOP_N]
        return {'summary': summary, 'columns': columns, 'rows': rows}

    # ==================================================================
    # 6. Carry Forward Order Report — Date > Machine.
    # ==================================================================
    @api.model
    def _data_carry_forward_order(self, ctx):
        domain = [
            ('date', '>=', ctx['date_from']), ('date', '<=', ctx['date_to']),
            ('source', '=', 'carry_forward'),
            ('company_id', '=', ctx['company'].id),
        ]
        if ctx['departments']:
            domain.append(('department_id', 'in', ctx['departments'].ids))
        if ctx['workcenters']:
            domain.append(('workcenter_id', 'in', ctx['workcenters'].ids))
        records = self.env['fmes.production.plan.line'].search(
            domain, order='date, workcenter_id')

        running_by_machine = {}
        rows = []
        for line in records:
            machine = line.workcenter_id
            running_by_machine[machine] = (
                running_by_machine.get(machine, 0.0) + line.planned_qty)
            rows.append({
                'date': line.date,
                'workcenter_id': machine.name or '',
                'origin': (line.carry_forward_from_id.display_name
                          if line.carry_forward_from_id else ''),
                'product_id': line.product_id.display_name or '',
                'carried_qty': line.planned_qty,
                'new_date': line.date,
                'cumulative_qty': running_by_machine[machine],
            })
        summary = [
            {'label': _("Carried-Forward Lines"), 'value': len(rows), 'fmt': 'int'},
            {'label': _("Total Carried Quantity"),
             'value': sum(r['carried_qty'] for r in rows), 'fmt': 'qty'},
        ]
        columns = [
            {'key': 'date', 'label': _("Date"), 'fmt': 'date'},
            {'key': 'workcenter_id', 'label': _("Machine"), 'fmt': 'text'},
            {'key': 'origin', 'label': _("Origin Line"), 'fmt': 'text'},
            {'key': 'product_id', 'label': _("Product"), 'fmt': 'text'},
            {'key': 'carried_qty', 'label': _("Carried Qty"), 'fmt': 'qty'},
            {'key': 'new_date', 'label': _("New Date"), 'fmt': 'date'},
            {'key': 'cumulative_qty', 'label': _("Cumulative (Machine)"), 'fmt': 'qty'},
        ]
        if ctx['summary_only']:
            rows = rows[:TOP_N]
        return {'summary': summary, 'columns': columns, 'rows': rows}

    # ==================================================================
    # 7. Maintenance Report — Equipment > Month, native grain.
    # ==================================================================
    @api.model
    def _data_maintenance(self, ctx):
        month_from = ctx['date_from'].replace(day=1)
        domain = [
            ('month', '>=', month_from), ('month', '<=', ctx['date_to']),
            ('company_id', '=', ctx['company'].id),
            # Plant machinery only. maintenance.equipment covers every
            # asset the maintenance module tracks (including generic IT
            # equipment carried over from its own demo data); this report
            # is about machine health, so equipment with no mrp.workcenter
            # behind it is out of scope, the same way docs/11's own
            # "Equipment > Month" grouping implies a machine exists.
            ('workcenter_id', '!=', False),
        ]
        if ctx['departments']:
            domain.append(('department_id', 'in', ctx['departments'].ids))
        if ctx['workcenters']:
            domain.append(('workcenter_id', 'in', ctx['workcenters'].ids))
        rows = self.env['fmes.maintenance.report'].search_read(
            domain,
            ['month', 'equipment_id', 'preventive_count', 'corrective_count',
             'pm_compliance_pct', 'has_pm_due', 'mtbf', 'mttr',
             'downtime_hours', 'cost', 'overdue_count'],
            order='equipment_id, month')
        summary = [
            {'label': _("PM Requests"),
             'value': sum(r['preventive_count'] for r in rows), 'fmt': 'int'},
            {'label': _("Breakdown Requests"),
             'value': sum(r['corrective_count'] for r in rows), 'fmt': 'int'},
            {'label': _("Total Downtime Hours"),
             'value': sum(r['downtime_hours'] for r in rows), 'fmt': 'hours'},
            {'label': _("Total Cost"),
             'value': sum(r['cost'] for r in rows), 'fmt': 'qty'},
            {'label': _("Currently Overdue"),
             'value': sum(r['overdue_count'] for r in rows), 'fmt': 'int'},
        ]
        columns = [
            {'key': 'equipment_id', 'label': _("Equipment"), 'fmt': 'text'},
            {'key': 'month', 'label': _("Month"), 'fmt': 'date'},
            {'key': 'preventive_count', 'label': _("PM"), 'fmt': 'int'},
            {'key': 'corrective_count', 'label': _("Breakdown"), 'fmt': 'int'},
            {'key': 'pm_compliance_pct', 'label': _("PM Compliance %"), 'fmt': 'pct'},
            {'key': 'mtbf', 'label': _("MTBF (days)"), 'fmt': 'int'},
            {'key': 'mttr', 'label': _("MTTR (days)"), 'fmt': 'int'},
            {'key': 'downtime_hours', 'label': _("Downtime Hrs"), 'fmt': 'hours'},
            {'key': 'cost', 'label': _("Cost"), 'fmt': 'qty'},
        ]
        table_rows = [{
            'equipment_id': r['equipment_id'][1] if r['equipment_id'] else '',
            'month': r['month'],
            'preventive_count': r['preventive_count'],
            'corrective_count': r['corrective_count'],
            'pm_compliance_pct': r['pm_compliance_pct'] if r['has_pm_due'] else None,
            'mtbf': r['mtbf'],
            'mttr': r['mttr'],
            'downtime_hours': r['downtime_hours'],
            'cost': r['cost'],
        } for r in rows]
        if ctx['summary_only']:
            table_rows = sorted(
                table_rows, key=lambda r: r['downtime_hours'],
                reverse=True)[:TOP_N]
        return {'summary': summary, 'columns': columns, 'rows': table_rows}

    # ==================================================================
    # 8. Productivity Report — Department > Shift. Merges
    #    fmes.production.report (output, manpower-hours -> productivity)
    #    with fmes.manpower.impact.report (headcount, shortage) by the
    #    same (department, shift) key — the two halves of docs/11's own
    #    column list for this report.
    # ==================================================================
    @api.model
    def _data_productivity(self, ctx):
        prod_domain = self._domain(ctx)
        prod_data = self.env['fmes.production.report']._read_group(
            prod_domain, groupby=['department_id', 'shift_id'],
            aggregates=['ok_qty:sum', 'manpower_hours:sum'])
        by_key = {}
        for department, shift, ok_qty, manpower_hours in prod_data:
            by_key[(department.id, shift.id)] = {
                'department_id': department.name or '',
                'shift_id': shift.name if shift else '',
                'ok_qty': ok_qty or 0.0,
                'manpower_hours': manpower_hours or 0.0,
                'std_manpower': 0.0, 'actual_manpower': 0.0,
            }

        impact_domain = self._domain(
            ctx, dept_field='department_id', wc_field=None,
            product_field=None)
        impact_data = self.env['fmes.manpower.impact.report']._read_group(
            impact_domain, groupby=['department_id', 'shift_id'],
            aggregates=['std_manpower:sum', 'actual_manpower:sum'])
        for department, shift, std_manpower, actual_manpower in impact_data:
            key = (department.id, shift.id)
            entry = by_key.setdefault(key, {
                'department_id': department.name or '',
                'shift_id': shift.name if shift else '',
                'ok_qty': 0.0, 'manpower_hours': 0.0,
                'std_manpower': 0.0, 'actual_manpower': 0.0,
            })
            entry['std_manpower'] = std_manpower or 0.0
            entry['actual_manpower'] = actual_manpower or 0.0

        rows = []
        for entry in by_key.values():
            entry['productivity'] = self._safe_div(
                entry['ok_qty'], entry['manpower_hours'])
            entry['manpower_utilization_pct'] = self._safe_div(
                entry['actual_manpower'], entry['std_manpower'], 100.0)
            entry['shortage'] = entry['std_manpower'] - entry['actual_manpower']
            rows.append(entry)

        total_ok = sum(r['ok_qty'] for r in rows)
        total_mp_hours = sum(r['manpower_hours'] for r in rows)
        summary = [
            {'label': _("Total Good Output"), 'value': total_ok, 'fmt': 'qty'},
            {'label': _("Overall Productivity (units/mp-hr)"),
             'value': self._safe_div(total_ok, total_mp_hours), 'fmt': 'qty'},
            {'label': _("Total Manpower Shortage"),
             'value': sum(r['shortage'] for r in rows), 'fmt': 'qty'},
        ]
        columns = [
            {'key': 'department_id', 'label': _("Department"), 'fmt': 'text'},
            {'key': 'shift_id', 'label': _("Shift"), 'fmt': 'text'},
            {'key': 'ok_qty', 'label': _("Output"), 'fmt': 'qty'},
            {'key': 'std_manpower', 'label': _("Std Manpower"), 'fmt': 'qty'},
            {'key': 'actual_manpower', 'label': _("Actual Manpower"), 'fmt': 'qty'},
            {'key': 'manpower_utilization_pct', 'label': _("Manpower Util %"), 'fmt': 'pct'},
            {'key': 'productivity', 'label': _("Units / Manpower-hr"), 'fmt': 'qty'},
            {'key': 'shortage', 'label': _("Shortage Impact"), 'fmt': 'qty'},
        ]
        if ctx['summary_only']:
            rows = sorted(
                rows, key=lambda r: r['productivity'], reverse=True)[:TOP_N]
        return {'summary': summary, 'columns': columns, 'rows': rows}

    # ==================================================================
    # 9. Exception Report — grouped by exception (alert) type, one
    #    consolidated action list (docs/11 section 4, report 9).
    # ==================================================================
    @api.model
    def _data_exception(self, ctx):
        # fmes.alert has no stored department_id (Phase 11's own documented
        # simplification — a polymorphic res_model/res_id, not easily
        # expressed as a plain domain field), so the wizard's department
        # and machine filters do not apply here; every exception in the
        # period is included regardless.
        domain = [
            ('alert_type', 'in', EXCEPTION_ALERT_TYPES),
            ('triggered_on', '>=', ctx['date_from']),
            ('triggered_on', '<=', ctx['date_to']),
            ('company_id', '=', ctx['company'].id),
        ]
        records = self.env['fmes.alert'].search(
            domain, order='alert_type, severity desc, triggered_on desc')
        alert_type_labels = dict(ALERT_TYPES)
        rows = [{
            'alert_type': alert_type_labels.get(
                record.alert_type, record.alert_type),
            'severity': record.severity,
            'subject': record.subject,
            'triggered_on': record.triggered_on,
            'state': record.state,
        } for record in records]
        by_severity = {}
        for record in records:
            by_severity[record.severity] = by_severity.get(record.severity, 0) + 1
        summary = [
            {'label': _("Total Exceptions"), 'value': len(records), 'fmt': 'int'},
            {'label': _("Critical"), 'value': by_severity.get('critical', 0), 'fmt': 'int'},
            {'label': _("Warning"), 'value': by_severity.get('warning', 0), 'fmt': 'int'},
            {'label': _("Still Open"),
             'value': len(records.filtered(lambda a: a.state == 'new')),
             'fmt': 'int'},
        ]
        columns = [
            {'key': 'alert_type', 'label': _("Exception Type"), 'fmt': 'text'},
            {'key': 'severity', 'label': _("Severity"), 'fmt': 'text'},
            {'key': 'subject', 'label': _("Subject"), 'fmt': 'text'},
            {'key': 'triggered_on', 'label': _("Triggered On"), 'fmt': 'text'},
            {'key': 'state', 'label': _("Status"), 'fmt': 'text'},
        ]
        if ctx['summary_only']:
            rows = rows[:TOP_N]
        return {'summary': summary, 'columns': columns, 'rows': rows}

    # ==================================================================
    # 10. Monthly Management MIS — an executive summary, then a
    #     summary-only section per report above, plus month-on-month
    #     comparison of the headline KPIs.
    # ==================================================================
    @api.model
    def _data_monthly_mis(self, ctx):
        sections = []
        for report_type in MIS_SECTION_TYPES:
            method = getattr(self, '_data_%s' % report_type)
            section_ctx = dict(ctx, summary_only=True)
            section = method(section_ctx)
            section['report_type'] = report_type
            section['title'] = REPORT_TITLES.get(report_type, report_type)
            sections.append(section)

        prod_domain = self._domain(ctx)
        current = self.env['fmes.production.report']._read_group(
            prod_domain, aggregates=['planned_qty:sum', 'actual_qty:sum'])
        cur_planned, cur_actual = current[0] if current else (0.0, 0.0)

        prev_from, prev_to = self._previous_period(
            ctx['date_from'], ctx['date_to'])
        prev_ctx = dict(ctx, date_from=prev_from, date_to=prev_to)
        prev_domain = self._domain(prev_ctx)
        previous = self.env['fmes.production.report']._read_group(
            prev_domain, aggregates=['planned_qty:sum', 'actual_qty:sum'])
        prev_planned, prev_actual = previous[0] if previous else (0.0, 0.0)

        summary = [
            {'label': _("Achievement % (This Period)"),
             'value': self._safe_div(cur_actual or 0.0, cur_planned or 0.0, 100.0),
             'fmt': 'pct'},
            {'label': _("Achievement % (Previous Period)"),
             'value': self._safe_div(prev_actual or 0.0, prev_planned or 0.0, 100.0),
             'fmt': 'pct'},
        ]
        return {
            'summary': summary, 'columns': [], 'rows': [],
            'sections': sections,
        }

    # ==================================================================
    # XLSX (deliverable 2) — same `get_report_data` dict PDF rendering
    # uses, written with raw numeric values and a per-column number
    # format rather than `format_value`'s display strings, so a
    # recipient can still sort and filter the sheet in Excel (mirrors
    # `controllers/plan_export.py`'s own established pattern).
    # ==================================================================
    @api.model
    def xlsx_formats(self, workbook):
        return {
            'title': workbook.add_format(
                {'bold': True, 'font_size': 14, 'font_color': '#0e2238'}),
            'subtitle': workbook.add_format(
                {'italic': True, 'font_color': '#555555'}),
            'header': workbook.add_format(
                {'bold': True, 'bg_color': '#0e2238', 'font_color': '#ffffff',
                 'border': 1, 'align': 'center', 'valign': 'vcenter',
                 'text_wrap': True}),
            'label': workbook.add_format({'bold': True}),
            'text': workbook.add_format({}),
            'date': workbook.add_format({'num_format': 'yyyy-mm-dd'}),
            'qty': workbook.add_format({'num_format': '#,##0.00'}),
            'hours': workbook.add_format({'num_format': '#,##0.00'}),
            'int': workbook.add_format({'num_format': '#,##0'}),
            'pct': workbook.add_format({'num_format': '0.0"%"'}),
        }

    @api.model
    def write_xlsx(self, workbook, data):
        fmt = self.xlsx_formats(workbook)
        self._write_parameters_sheet(workbook, fmt, data)
        if data.get('sections'):
            for section in data['sections']:
                self._write_section_sheet(
                    workbook, fmt, section, section['title'][:31])
        else:
            self._write_section_sheet(workbook, fmt, data, 'Report')

    @api.model
    def _write_parameters_sheet(self, workbook, fmt, data):
        sheet = workbook.add_worksheet('Parameters')
        sheet.set_column(0, 0, 22)
        sheet.set_column(1, 1, 60)
        rows = [
            ('Report', data.get('title', '')),
            ('Period', data.get('period_label', '')),
            ('Filters', data.get('filters_label', '')),
            ('Company', data['company'].name if data.get('company') else ''),
            ('Generated On', str(data.get('generated_on', ''))),
        ]
        for row, (label, value) in enumerate(rows):
            sheet.write(row, 0, label, fmt['label'])
            sheet.write(row, 1, value, fmt['text'])

    @api.model
    def _write_section_sheet(self, workbook, fmt, section, sheet_name):
        sheet = workbook.add_worksheet(sheet_name)
        sheet.write(0, 0, section.get('title', ''), fmt['title'])

        row = 2
        for entry in section.get('summary', []):
            sheet.write(row, 0, entry['label'], fmt['label'])
            self._write_cell(sheet, row, 1, fmt, entry['value'], entry['fmt'])
            row += 1
        row += 1

        columns = section.get('columns', [])
        if not columns:
            return
        for col, column in enumerate(columns):
            sheet.write(row, col, column['label'], fmt['header'])
            sheet.set_column(col, col, 18)
        header_row = row
        row += 1
        for record in section.get('rows', []):
            for col, column in enumerate(columns):
                self._write_cell(
                    sheet, row, col, fmt, record.get(column['key']),
                    column['fmt'])
            row += 1
        sheet.freeze_panes(header_row + 1, 0)
        if row > header_row + 1:
            sheet.autofilter(header_row, 0, row - 1, len(columns) - 1)

    @api.model
    def _write_cell(self, sheet, row, col, fmt, value, kind):
        if value in (None, False) and kind != 'text':
            sheet.write(row, col, None)
            return
        if kind == 'date' and value:
            sheet.write_datetime(row, col, value, fmt['date'])
        elif kind in ('qty', 'hours', 'pct'):
            sheet.write_number(row, col, value or 0.0, fmt[kind])
        elif kind == 'int':
            sheet.write_number(row, col, value or 0, fmt['int'])
        else:
            sheet.write(row, col, value or '', fmt['text'])


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
