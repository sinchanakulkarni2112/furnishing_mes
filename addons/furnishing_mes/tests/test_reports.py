# -*- coding: utf-8 -*-
"""Phase 12 tests: the reporting suite (Requirement 12).

Two things matter most here. Every one of the ten report types must render
without error against real, approved data (deliverable 7's first half) —
this is the same "each report renders for the demo dataset" the phase's
own exit criteria names, exercised here against a small fixture plant
rather than the demo dataset itself, for the same reason `tests/common.py`
never depends on demo data anywhere else in this module: demo figures get
tuned, fixture figures do not. And a report's own summary figure must equal
what the Executive Dashboard (Phase 10) computes for the exact same
underlying rows (deliverable 7's second half, "figures reconcile with the
dashboard") — both read `fmes.production.report` the same sum-then-divide
way, so if they ever disagreed it would mean one of them stopped following
D0.7, not that the numbers are simply "different views."
"""

from datetime import datetime, time, timedelta

from odoo import fields
from odoo.tests import tagged

from .common import FmesTestCase


class ReportCase(FmesTestCase):
    """A fixture plant with one entry of real data for every report type."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env['fmes.report.service']
        cls.today = fields.Date.context_today(cls.env.user)

        # ---------------------------------------------------- production
        cls.entry = cls.env['fmes.production.entry'].create({
            'date': cls.today, 'shift_id': cls.shift_a.id,
            'workcenter_id': cls.wc_saw.id,
            'product_id': cls.product_wardrobe.id,
            'planned_qty': 100.0, 'actual_qty': 80.0, 'rejected_qty': 5.0,
        })
        cls.entry.action_submit()
        cls.entry.action_approve()

        # ------------------------------------------------------ downtime
        start = datetime.combine(cls.today, time(8, 0))
        cls.downtime_event = cls.env['mrp.workcenter.productivity'].create({
            'workcenter_id': cls.wc_saw.id,
            'loss_id': cls.env.ref('mrp.block_reason1').id,
            'fmes_shift_id': cls.shift_a.id,
            'date_start': start, 'date_end': start + timedelta(hours=1),
            'fmes_state': 'approved',
        })

        # ---------------------------------------------------- manpower
        cls.manpower_log = cls.env['fmes.manpower.log'].create({
            'date': cls.today, 'shift_id': cls.shift_a.id,
            'department_id': cls.dept_cutting.id,
            'std_manpower': 4.0, 'actual_manpower': 3.0,
        })

        # -------------------------------------------------- maintenance
        cls.maintenance_request = cls.env['maintenance.request'].create({
            'name': 'Test PM', 'equipment_id': cls.equipment_saw.id,
            'maintenance_type': 'preventive',
            'request_date': cls.today, 'fmes_due_date': cls.today,
            'fmes_cost': 1500.0,
        })

        # ------------------------------------------------------- backlog
        cls.mo = cls.env['mrp.production'].create({
            'product_id': cls.product_wardrobe.id, 'product_qty': 50.0,
        })
        cls.backlog_row = cls.env['fmes.backlog.snapshot'].create({
            'snapshot_date': cls.today, 'production_id': cls.mo.id,
            'product_id': cls.product_wardrobe.id,
            'department_id': cls.dept_cutting.id,
            'workcenter_id': cls.wc_saw.id,
            'ordered_qty': 50.0, 'produced_qty': 10.0, 'pending_qty': 40.0,
            'date_deadline': cls.today - timedelta(days=20),
            'days_delayed': 20, 'status': 'delayed', 'is_critical': True,
            'company_id': cls.company.id,
        })

        # ---------------------------------------------------- carry-forward
        cls.plan = cls.env['fmes.production.plan'].create({
            'plan_type': 'daily', 'date_from': cls.today, 'date_to': cls.today,
        })
        cls.carry_forward_line = cls.env['fmes.production.plan.line'].create({
            'plan_id': cls.plan.id, 'date': cls.today,
            'shift_id': cls.shift_a.id, 'workcenter_id': cls.wc_saw.id,
            'product_id': cls.product_wardrobe.id, 'planned_qty': 15.0,
            'source': 'carry_forward',
        })

        # ------------------------------------------------------- alert
        cls.alert_rule = cls.env['fmes.alert.rule'].create({
            'name': 'Test Target Rule', 'alert_type': 'target_not_achieved',
            'operator': 'lt', 'threshold': 95.0,
        })
        cls.alert = cls.env['fmes.alert'].create({
            'rule_id': cls.alert_rule.id, 'severity': 'warning',
            'subject': 'Test exception', 'triggered_on': fields.Datetime.now(),
            'res_model': 'mrp.workcenter', 'res_id': cls.wc_saw.id,
            'measured_value': 80.0, 'threshold_value': 95.0,
            'company_id': cls.company.id,
        })

    def _period(self):
        return self.today - timedelta(days=1), self.today + timedelta(days=1)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase12')
class TestReportsRenderWithoutError(ReportCase):
    """Deliverable 7, first half: every report type produces a result."""

    def test_all_ten_report_types_return_data(self):
        date_from, date_to = self._period()
        for report_type in [
                'daily_production', 'machine_utilisation',
                'production_output_summary', 'downtime', 'backlog',
                'carry_forward_order', 'maintenance', 'productivity',
                'exception', 'monthly_mis']:
            data = self.service.get_report_data(
                report_type, date_from, date_to)
            self.assertTrue(data['title'], report_type)
            self.assertIn('summary', data)

    def test_daily_production_has_the_fixture_entry(self):
        date_from, date_to = self._period()
        data = self.service.get_report_data(
            'daily_production', date_from, date_to)
        self.assertEqual(len(data['rows']), 1)
        self.assertEqual(data['rows'][0]['actual_qty'], 80.0)

    def test_backlog_shows_the_latest_snapshot(self):
        date_from, date_to = self._period()
        data = self.service.get_report_data('backlog', date_from, date_to)
        self.assertEqual(len(data['rows']), 1)
        self.assertEqual(data['rows'][0]['pending_qty'], 40.0)
        self.assertEqual(data['rows'][0]['days_delayed'], 20)

    def test_carry_forward_report_shows_the_carried_line(self):
        date_from, date_to = self._period()
        data = self.service.get_report_data(
            'carry_forward_order', date_from, date_to)
        self.assertEqual(len(data['rows']), 1)
        self.assertEqual(data['rows'][0]['carried_qty'], 15.0)

    def test_exception_report_groups_by_alert_type(self):
        date_from = fields.Date.to_date(
            fields.Datetime.now() - timedelta(days=1))
        date_to = fields.Date.to_date(
            fields.Datetime.now() + timedelta(days=1))
        data = self.service.get_report_data('exception', date_from, date_to)
        self.assertEqual(len(data['rows']), 1)
        self.assertEqual(data['rows'][0]['subject'], 'Test exception')

    def test_monthly_mis_has_seven_sections(self):
        date_from, date_to = self._period()
        data = self.service.get_report_data(
            'monthly_mis', date_from, date_to)
        self.assertEqual(len(data['sections']), 7)
        for section in data['sections']:
            self.assertTrue(section['title'])

    def test_maintenance_report_reads_the_pm_request(self):
        date_from, date_to = self._period()
        data = self.service.get_report_data(
            'maintenance', date_from, date_to)
        self.assertEqual(len(data['rows']), 1)
        self.assertEqual(data['rows'][0]['cost'], 1500.0)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase12')
class TestReportsReconcileWithDashboard(ReportCase):
    """Deliverable 7, second half."""

    def test_production_output_summary_matches_dashboard_achievement(self):
        date_from, date_to = self._period()
        report_data = self.service.get_report_data(
            'production_output_summary', date_from, date_to)
        report_achievement = next(
            entry['value'] for entry in report_data['summary']
            if entry['label'] == 'Achievement %')

        dashboard_data = self.env['fmes.dashboard.service'].get_dashboard_data(
            date_from, date_to)
        dashboard_achievement = dashboard_data['kpis']['achievement_pct']['value']

        self.assertAlmostEqual(
            report_achievement, dashboard_achievement, places=1)


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase12')
class TestReportRendering(ReportCase):
    """Deliverable 1/2: the PDF and XLSX actually render, not just the
    underlying data dict."""

    def test_report_template_renders(self):
        # _render_qweb_pdf falls back to HTML under test_enable unless
        # force_report_rendering is set — deliberately NOT set here. Forcing
        # an actual wkhtmltopdf run deadlocks under the CLI test runner (it
        # needs to fetch the rendered page over HTTP from the same
        # single-threaded process that is waiting on it), so real PDF bytes
        # are verified once by hand via `odoo shell` instead (see
        # docs/06-build-plan.md's own note on this, matching the same
        # "no browser available" precedent Phase 10 already established).
        # This still exercises the exact same QWeb template and the same
        # `_get_report_values` -> `get_report_data` pipeline PDF rendering
        # uses — the class of bug Phase 11 found (a QWeb expression that
        # only fails to compile at actual render time) is still caught here.
        wizard = self.env['fmes.report.wizard'].create({
            'report_type': 'daily_production',
            'date_from': self.today, 'date_to': self.today,
        })
        content, report_type = self.env['ir.actions.report']._render_qweb_pdf(
            'furnishing_mes.action_report_fmes_generic', wizard.ids)
        self.assertEqual(report_type, 'html')
        self.assertIn(b'Daily Production Report', content)

    def test_monthly_mis_template_renders_every_section(self):
        wizard = self.env['fmes.report.wizard'].create({
            'report_type': 'monthly_mis',
            'date_from': self.today, 'date_to': self.today,
        })
        content, report_type = self.env['ir.actions.report']._render_qweb_pdf(
            'furnishing_mes.action_report_fmes_generic', wizard.ids)
        self.assertEqual(report_type, 'html')
        self.assertIn(b'Monthly Management MIS', content)
        self.assertIn(b'Downtime Report', content)
        self.assertIn(b'Exception Report', content)

    def test_xlsx_writes_a_workbook(self):
        import io
        import xlsxwriter
        date_from, date_to = self._period()
        data = self.service.get_report_data(
            'daily_production', date_from, date_to)
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        self.service.write_xlsx(workbook, data)
        workbook.close()
        self.assertTrue(output.getvalue())

    def test_xlsx_writes_all_mis_sections(self):
        import io
        import xlsxwriter
        date_from, date_to = self._period()
        data = self.service.get_report_data(
            'monthly_mis', date_from, date_to)
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        self.service.write_xlsx(workbook, data)
        workbook.close()
        sheet_names = [sheet.name for sheet in workbook.worksheets()]
        self.assertIn('Parameters', sheet_names)
        self.assertEqual(len(sheet_names), 1 + len(data['sections']))


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase12')
class TestReportWizard(ReportCase):

    def test_xlsx_format_returns_an_act_url(self):
        wizard = self.env['fmes.report.wizard'].create({
            'report_type': 'daily_production',
            'date_from': self.today, 'date_to': self.today, 'format': 'xlsx',
        })
        action = wizard.action_generate()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertIn('/fmes/report/xlsx/%d' % wizard.id, action['url'])

    def test_pdf_format_returns_a_report_action(self):
        wizard = self.env['fmes.report.wizard'].create({
            'report_type': 'daily_production',
            'date_from': self.today, 'date_to': self.today, 'format': 'pdf',
        })
        action = wizard.action_generate()
        self.assertEqual(action['report_name'],
                         'furnishing_mes.report_fmes_generic')

    def test_end_date_before_start_date_is_rejected(self):
        from odoo.exceptions import UserError
        wizard = self.env['fmes.report.wizard'].create({
            'report_type': 'daily_production',
            'date_from': self.today, 'date_to': self.today - timedelta(days=1),
        })
        with self.assertRaises(UserError):
            wizard.action_generate()


@tagged('post_install', '-at_install', 'fmes', 'fmes_phase12')
class TestReportSchedule(ReportCase):

    def _schedule(self, **vals):
        base = {
            'name': 'Test Schedule', 'report_type': 'daily_production',
            'frequency': 'daily', 'run_time': 7.0,
            'period_offset': 'yesterday', 'format': 'pdf',
        }
        base.update(vals)
        return self.env['fmes.report.schedule'].create(base)

    def test_daily_next_run_is_tomorrow_at_run_time(self):
        schedule = self._schedule(run_time=7.5)
        after = datetime(2026, 3, 10, 9, 0, 0)
        next_run = schedule._compute_next_run(after)
        self.assertEqual(next_run, datetime(2026, 3, 11, 7, 30, 0))

    def test_daily_next_run_today_if_still_ahead(self):
        schedule = self._schedule(run_time=18.0)
        after = datetime(2026, 3, 10, 9, 0, 0)
        next_run = schedule._compute_next_run(after)
        self.assertEqual(next_run, datetime(2026, 3, 10, 18, 0, 0))

    def test_weekly_next_run_lands_on_the_chosen_weekday(self):
        # 2026-03-10 is a Tuesday; day_of_week '0' is Monday.
        schedule = self._schedule(
            frequency='weekly', day_of_week='0', run_time=8.0)
        after = datetime(2026, 3, 10, 9, 0, 0)
        next_run = schedule._compute_next_run(after)
        self.assertEqual(next_run, datetime(2026, 3, 16, 8, 0, 0))
        self.assertEqual(next_run.weekday(), 0)

    def test_monthly_next_run_lands_on_the_chosen_day(self):
        schedule = self._schedule(
            frequency='monthly', day_of_month=1, run_time=9.0)
        after = datetime(2026, 3, 10, 9, 0, 0)
        next_run = schedule._compute_next_run(after)
        self.assertEqual(next_run, datetime(2026, 4, 1, 9, 0, 0))

    def test_period_offset_yesterday(self):
        schedule = self._schedule(period_offset='yesterday')
        as_of = datetime(2026, 3, 10, 7, 0, 0)
        date_from, date_to = schedule._compute_period(as_of)
        self.assertEqual(date_from, date_to)
        self.assertEqual(date_from.isoformat(), '2026-03-09')

    def test_period_offset_last_month(self):
        schedule = self._schedule(period_offset='last_month')
        as_of = datetime(2026, 3, 10, 9, 0, 0)
        date_from, date_to = schedule._compute_period(as_of)
        self.assertEqual(date_from.isoformat(), '2026-02-01')
        self.assertEqual(date_to.isoformat(), '2026-02-28')

    def test_no_recipients_is_a_no_op_not_a_failure(self):
        schedule = self._schedule(recipient_ids=[(6, 0, [])])
        mail_count_before = self.env['mail.mail'].search_count([])
        schedule._send_scheduled_report(fields.Datetime.now())
        self.assertEqual(
            self.env['mail.mail'].search_count([]), mail_count_before)

    def test_cron_sends_mail_with_attachment_to_configured_recipient(self):
        partner = self.env['res.partner'].create({
            'name': 'Test Recipient', 'email': 'test.recipient@example.com'})
        schedule = self._schedule(
            recipient_ids=[(6, 0, [partner.id])], format='pdf')
        before = fields.Datetime.now()
        self.env['fmes.report.schedule']._cron_send_scheduled_reports()
        schedule.invalidate_recordset(['last_run', 'next_run'])
        self.assertTrue(schedule.last_run)
        self.assertGreater(schedule.next_run, before)
        mail = self.env['mail.mail'].search(
            [('recipient_ids', 'in', partner.id)], limit=1)
        self.assertTrue(mail)
        self.assertTrue(mail.attachment_ids)

    def test_cron_advances_next_run_even_when_a_schedule_has_no_recipients(self):
        schedule = self._schedule(recipient_ids=[(6, 0, [])])
        old_next_run = schedule.next_run
        self.env['fmes.report.schedule']._cron_send_scheduled_reports()
        schedule.invalidate_recordset(['next_run'])
        self.assertNotEqual(schedule.next_run, old_next_run)

    def test_notify_failure_raises_an_activity_for_the_manager(self):
        manager = self._create_user(
            'fmes_report_mgr', 'furnishing_mes.group_fmes_manager')
        schedule = self._schedule()
        schedule._notify_failure(RuntimeError('boom'))
        manager_activities = schedule.activity_ids.filtered(
            lambda a: a.user_id == manager)
        self.assertTrue(manager_activities)
        self.assertIn('boom', manager_activities[0].note)

    def test_action_run_now_sends_immediately(self):
        partner = self.env['res.partner'].create({
            'name': 'Test Recipient 2', 'email': 'test.recipient2@example.com'})
        schedule = self._schedule(recipient_ids=[(6, 0, [partner.id])])
        mail_count_before = self.env['mail.mail'].search_count([])
        schedule.action_run_now()
        self.assertGreater(
            self.env['mail.mail'].search_count([]), mail_count_before)
