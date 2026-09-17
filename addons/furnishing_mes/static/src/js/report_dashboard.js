/** @odoo-module **/
/**
 * Report Dashboard.
 *
 * A chart-and-KPI landing page in front of the eight existing on-demand
 * reports (`fmes.report.wizard` / `fmes.report.service`), so opening one of
 * those Analytics menu items shows graphs and percentages first instead of
 * immediately popping a bare date-range form. Nothing here computes a
 * figure of its own: the KPI tiles and every chart read numbers already
 * produced by `fmes.report.service.get_report_data` (the exact same call
 * the PDF and XLSX use) and `fmes.dashboard.service.get_dashboard_data`
 * (the Executive Dashboard's own service) — a chart on this page and the
 * PDF someone downloads from it can never disagree.
 *
 * Download buttons create a real `fmes.report.wizard` record with this
 * page's own date range and call its existing `action_generate` — the same
 * method the wizard's own form button calls — so PDF and XLSX generation
 * is not reimplemented here at all, only triggered.
 */

import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";

const DAY_MS = 24 * 60 * 60 * 1000;

function toISO(date) {
    return date.toISOString().slice(0, 10);
}

function startOfWeek(date) {
    const day = date.getDay();
    const diff = (day + 6) % 7; // Monday-start week.
    return new Date(date.getTime() - diff * DAY_MS);
}

function periodRange(preset, customFrom, customTo) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    if (preset === "today") {
        return [toISO(today), toISO(today)];
    }
    if (preset === "week") {
        return [toISO(startOfWeek(today)), toISO(today)];
    }
    if (preset === "month") {
        return [toISO(new Date(today.getFullYear(), today.getMonth(), 1)), toISO(today)];
    }
    if (preset === "quarter") {
        const qStartMonth = Math.floor(today.getMonth() / 3) * 3;
        return [toISO(new Date(today.getFullYear(), qStartMonth, 1)), toISO(today)];
    }
    return [customFrom || toISO(today), customTo || toISO(today)];
}

const CHART_COLORS = {
    achievement: "#3498db",
    target: "#95a5a6",
    success: "#28a745",
    warning: "#f0ad4e",
    danger: "#dc3545",
};

// Which dashboard_service tile each report reuses for its chart, and how to
// draw it. "summary_bar" needs no dashboard_service call at all — it charts
// the report's own already-computed `summary` percentages directly.
const CHART_MAP = {
    daily_production: { title: _t("Production Trend"), kind: "trend" },
    machine_utilisation: { title: _t("Machine Utilisation Ranking"), kind: "ranking" },
    downtime: { title: _t("Downtime Pareto"), kind: "pareto" },
    backlog: { title: _t("Backlog Ageing"), kind: "ageing" },
    productivity: { title: _t("Productivity Trend"), kind: "productivity" },
    maintenance: { title: _t("Maintenance Performance"), kind: "maintenance" },
    exception: { title: _t("Exceptions by Severity"), kind: "summary_bar" },
    monthly_mis: { title: _t("Achievement: This Period vs Previous"), kind: "summary_bar" },
};

const NEEDS_DASHBOARD_DATA = new Set([
    "daily_production", "machine_utilisation", "downtime", "backlog",
    "productivity", "maintenance",
]);

const REPORT_BLURBS = {
    daily_production: _t(
        "How much of the plan was actually produced each day, and where the shortfall is."),
    machine_utilisation: _t(
        "Which machines are running versus idle, ranked against the utilisation target."),
    downtime: _t(
        "Which downtime reasons cost the most hours, highest impact first."),
    backlog: _t(
        "How many open orders are pending, and how long they have been waiting."),
    productivity: _t("Output per manpower-hour over the selected period."),
    maintenance: _t(
        "Preventive maintenance compliance and machine reliability (MTBF/MTTR)."),
    exception: _t("Open threshold-breach alerts by severity for the selected period."),
    monthly_mis: _t(
        "A consolidated view of production, machine, downtime, backlog, maintenance, " +
        "productivity and exception performance for the period."),
};

export class FmesReportDashboard extends Component {
    static template = "furnishing_mes.ReportDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.mainChartRef = useRef("mainChartCanvas");
        this.chart = null;

        const context = this.props.action.context || {};
        this.reportType = context.report_type || "daily_production";

        const [dateFrom, dateTo] = periodRange("month");
        this.state = useState({
            preset: "month",
            dateFrom,
            dateTo,
            loading: true,
            downloading: false,
            data: null,
            dashboardData: null,
        });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });

        useEffect(
            () => this.renderChart(),
            () => [this.state.data, this.state.dashboardData]
        );
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------
    async load() {
        this.state.loading = true;
        try {
            const [reportData, dashboardData] = await Promise.all([
                this.orm.call(
                    "fmes.report.service", "get_report_data",
                    [this.reportType, this.state.dateFrom, this.state.dateTo],
                    { summary_only: true }),
                NEEDS_DASHBOARD_DATA.has(this.reportType)
                    ? this.orm.call(
                        "fmes.dashboard.service", "get_dashboard_data",
                        [this.state.dateFrom, this.state.dateTo])
                    : Promise.resolve(null),
            ]);
            this.state.data = reportData;
            this.state.dashboardData = dashboardData;
        } finally {
            this.state.loading = false;
        }
    }

    onPresetChange(ev) {
        const preset = ev.target.value;
        const [dateFrom, dateTo] = periodRange(preset, this.state.dateFrom, this.state.dateTo);
        this.state.preset = preset;
        this.state.dateFrom = dateFrom;
        this.state.dateTo = dateTo;
        this.load();
    }

    onCustomDateChange(field, ev) {
        this.state.preset = "custom";
        this.state[field] = ev.target.value;
        if (this.state.dateTo < this.state.dateFrom) {
            this.state.dateTo = this.state.dateFrom;
        }
        this.load();
    }

    async onRefresh() {
        await this.load();
    }

    get title() {
        return this.state.data ? this.state.data.title : "";
    }

    get explanation() {
        return REPORT_BLURBS[this.reportType] || "";
    }

    get chartKind() {
        return CHART_MAP[this.reportType].kind;
    }

    get chartTitle() {
        return CHART_MAP[this.reportType].title;
    }

    /** Mirrors `fmes.report.service.format_value` — the one place a figure
     * becomes displayed text there; this is the same rule applied
     * client-side so a KPI tile here reads the same as its PDF/XLSX
     * counterpart. */
    formatValue(value, fmt) {
        if ((value === null || value === undefined || value === false) && fmt !== "text") {
            if (fmt === "pct" || fmt === "hours" || fmt === "qty") {
                return "—";
            }
        }
        if (fmt === "pct") {
            return (value || 0).toFixed(1) + "%";
        }
        if (fmt === "hours" || fmt === "qty") {
            return (value || 0).toFixed(2);
        }
        if (fmt === "int") {
            return String(Math.round(value || 0));
        }
        if (fmt === "date") {
            return value ? String(value) : "";
        }
        return value === null || value === undefined || value === false ? "" : String(value);
    }

    // ------------------------------------------------------------------
    // Download — reuses the existing wizard's own PDF/XLSX generation
    // exactly, just triggered from here instead of from its popup form.
    // ------------------------------------------------------------------
    async downloadReport(format) {
        if (this.state.dateFrom > this.state.dateTo) {
            this.notification.add(
                _t("The start date must not be after the end date."),
                { type: "danger" });
            return;
        }
        this.state.downloading = true;
        try {
            const ids = await this.orm.create("fmes.report.wizard", [{
                report_type: this.reportType,
                date_from: this.state.dateFrom,
                date_to: this.state.dateTo,
                format,
            }]);
            const reportAction = await this.orm.call(
                "fmes.report.wizard", "action_generate", [ids]);
            await this.action.doAction(reportAction);
        } finally {
            this.state.downloading = false;
        }
    }

    // ------------------------------------------------------------------
    // Drill-through (parity with the Executive Dashboard's own charts)
    // ------------------------------------------------------------------
    drillTo(resModel, domain, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: resModel,
            views: [[false, "list"], [false, "pivot"], [false, "graph"]],
            domain,
        });
    }

    // ------------------------------------------------------------------
    // Charts
    // ------------------------------------------------------------------
    renderChart() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
        if (this.chartKind === "maintenance") {
            return;
        }
        const el = this.mainChartRef.el;
        if (!el) {
            return;
        }
        switch (this.chartKind) {
            case "trend":
                this._renderTrend(el);
                break;
            case "ranking":
                this._renderRanking(el);
                break;
            case "pareto":
                this._renderPareto(el);
                break;
            case "ageing":
                this._renderAgeing(el);
                break;
            case "productivity":
                this._renderProductivity(el);
                break;
            case "summary_bar":
                this._renderSummaryBar(el);
                break;
        }
    }

    _renderTrend(el) {
        const rows = this.state.dashboardData && this.state.dashboardData.production_trend;
        if (!rows) return;
        this.chart = new Chart(el, {
            type: "line",
            data: {
                labels: rows.map((r) => r.date),
                datasets: [
                    { label: _t("Planned"), data: rows.map((r) => r.planned_qty),
                      borderColor: CHART_COLORS.target, fill: false },
                    { label: _t("Actual"), data: rows.map((r) => r.actual_qty),
                      borderColor: CHART_COLORS.achievement, fill: false },
                ],
            },
            options: { responsive: true, maintainAspectRatio: false },
        });
    }

    _renderRanking(el) {
        const rows = this.state.dashboardData
            && this.state.dashboardData.machine_utilization_ranking;
        if (!rows) return;
        this.chart = new Chart(el, {
            type: "bar",
            data: {
                labels: rows.map((r) => r.machine),
                datasets: [{
                    label: _t("Utilisation %"),
                    data: rows.map((r) => r.utilization_pct),
                    backgroundColor: rows.map((r) => (
                        r.is_under_utilized ? CHART_COLORS.danger : CHART_COLORS.success)),
                }],
            },
            options: {
                indexAxis: "y",
                responsive: true, maintainAspectRatio: false,
                onClick: (_ev, elements) => {
                    if (elements.length) {
                        const row = rows[elements[0].index];
                        this.drillTo(
                            "fmes.utilization.report",
                            [["workcenter_id.display_name", "=", row.machine]], row.machine);
                    }
                },
            },
        });
    }

    _renderPareto(el) {
        const rows = this.state.dashboardData && this.state.dashboardData.downtime_pareto;
        if (!rows) return;
        this.chart = new Chart(el, {
            data: {
                labels: rows.map((r) => r.reason),
                datasets: [
                    { type: "bar", label: _t("Hours"), data: rows.map((r) => r.hours),
                      backgroundColor: CHART_COLORS.danger, yAxisID: "hours" },
                    { type: "line", label: _t("Cumulative %"),
                      data: rows.map((r) => r.cumulative_pct),
                      borderColor: CHART_COLORS.target, yAxisID: "pct", fill: false },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    hours: { type: "linear", position: "left" },
                    pct: { type: "linear", position: "right", min: 0, max: 100,
                           grid: { drawOnChartArea: false } },
                },
                onClick: (_ev, elements) => {
                    if (elements.length) {
                        const row = rows[elements[0].index];
                        this.drillTo(
                            "fmes.downtime.report",
                            [["loss_id.name", "=", row.reason]], row.reason);
                    }
                },
            },
        });
    }

    _renderAgeing(el) {
        const rows = this.state.dashboardData && this.state.dashboardData.backlog_ageing;
        if (!rows) return;
        const colors = { "0-3": CHART_COLORS.success, "4-7": CHART_COLORS.warning,
            "8-15": CHART_COLORS.warning, "15+": CHART_COLORS.danger };
        this.chart = new Chart(el, {
            type: "bar",
            data: {
                labels: rows.map((r) => r.bucket + " " + _t("days")),
                datasets: [{
                    label: _t("Pending Qty"),
                    data: rows.map((r) => r.pending_qty),
                    backgroundColor: rows.map((r) => colors[r.bucket]),
                }],
            },
            options: { responsive: true, maintainAspectRatio: false },
        });
    }

    _renderProductivity(el) {
        const rows = this.state.dashboardData && this.state.dashboardData.productivity_trend;
        if (!rows) return;
        this.chart = new Chart(el, {
            type: "line",
            data: {
                labels: rows.map((r) => r.date),
                datasets: [{
                    label: _t("Units / Manpower-Hour"),
                    data: rows.map((r) => r.units_per_manpower_hour),
                    borderColor: CHART_COLORS.achievement, fill: false,
                }],
            },
            options: { responsive: true, maintainAspectRatio: false },
        });
    }

    _renderSummaryBar(el) {
        const rows = (this.state.data.summary || []).filter(
            (entry) => entry.fmt === "pct" || entry.fmt === "int");
        if (!rows.length) return;
        this.chart = new Chart(el, {
            type: "bar",
            data: {
                labels: rows.map((r) => r.label),
                datasets: [{
                    label: _t("Value"),
                    data: rows.map((r) => r.value || 0),
                    backgroundColor: CHART_COLORS.achievement,
                }],
            },
            options: { responsive: true, maintainAspectRatio: false },
        });
    }
}

registry.category("actions").add("fmes_report_dashboard", FmesReportDashboard);
