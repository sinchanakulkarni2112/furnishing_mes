/** @odoo-module **/
/**
 * Executive Dashboard.
 *
 * Requirement 9, all ten metrics. Every number on this page is computed by
 * `fmes.dashboard.service` on the server — this component only renders what
 * it is given and turns a click into a filtered list/pivot/graph action on
 * the underlying report model. Nothing here re-derives a percentage; that
 * is what keeps a chart segment and its own drill-through list in agreement.
 *
 * One component serves both role variants (deliverable 3): a Plant Manager
 * sees the whole company by default, a Supervisor's own department scope
 * (`res.users.fmes_department_ids`) is pre-selected on load — identical
 * component, different starting filter, exactly as docs/05 section 3.3
 * describes it.
 */

import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { user } from "@web/core/user";
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
        const start = startOfWeek(today);
        return [toISO(start), toISO(today)];
    }
    if (preset === "month") {
        const start = new Date(today.getFullYear(), today.getMonth(), 1);
        return [toISO(start), toISO(today)];
    }
    if (preset === "quarter") {
        const qStartMonth = Math.floor(today.getMonth() / 3) * 3;
        const start = new Date(today.getFullYear(), qStartMonth, 1);
        return [toISO(start), toISO(today)];
    }
    return [customFrom || toISO(today), customTo || toISO(today)];
}

const CHART_COLORS = {
    achievement: "#3498db",
    target: "#95a5a6",
    success: "#28a745",
    warning: "#f0ad4e",
    danger: "#dc3545",
    info: "#3498db",
    idle: "#95a5a6",
};

export class FmesExecutiveDashboard extends Component {
    static template = "furnishing_mes.ExecutiveDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.productionTrendRef = useRef("productionTrendCanvas");
        this.downtimeParetoRef = useRef("downtimeParetoCanvas");
        this.departmentPerfRef = useRef("departmentPerfCanvas");
        this.shiftPerfRef = useRef("shiftPerfCanvas");
        this.machineRankingRef = useRef("machineRankingCanvas");
        this.backlogAgeingRef = useRef("backlogAgeingCanvas");
        this.productivityRef = useRef("productivityCanvas");
        this.charts = {};

        const [dateFrom, dateTo] = periodRange("month");
        this.state = useState({
            preset: "month",
            dateFrom,
            dateTo,
            departments: [],
            departmentIds: [],
            isManager: true,
            loading: true,
            data: null,
        });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            const [isManager, departments] = await Promise.all([
                user.hasGroup("furnishing_mes.group_fmes_manager"),
                this.orm.searchRead("hr.department", [], ["id", "name"]),
            ]);
            this.state.isManager = isManager;
            this.state.departments = departments;
            if (!isManager) {
                const [own] = await this.orm.read(
                    "res.users", [user.userId], ["fmes_department_ids"]);
                this.state.departmentIds = own.fmes_department_ids || [];
            }
            await this.load();
        });

        useEffect(
            () => this.renderCharts(),
            () => [this.state.data]
        );
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------
    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "fmes.dashboard.service", "get_dashboard_data",
                [this.state.dateFrom, this.state.dateTo],
                { department_ids: this.state.departmentIds || null });
        } finally {
            this.state.loading = false;
        }
    }

    onPresetChange(ev) {
        const preset = ev.target.value;
        const [dateFrom, dateTo] = periodRange(
            preset, this.state.dateFrom, this.state.dateTo);
        this.state.preset = preset;
        this.state.dateFrom = dateFrom;
        this.state.dateTo = dateTo;
        this.load();
    }

    onCustomDateChange(field, ev) {
        this.state.preset = "custom";
        this.state[field] = ev.target.value;
        this.load();
    }

    onDepartmentChange(ev) {
        const options = Array.from(ev.target.selectedOptions);
        this.state.departmentIds = options.map((o) => parseInt(o.value, 10));
        this.load();
    }

    async onRefresh() {
        await this.load();
    }

    /** The KPI row's own six tiles, in display order. A getter rather than
     * a literal array in the template — keeps the QWeb template itself
     * free of embedded JS data structures. */
    get kpiTiles() {
        const kpis = this.state.data.kpis;
        return [
            { key: "achievement_pct", label: _t("Achievement"), suffix: "%",
              kpi: kpis.achievement_pct },
            { key: "utilization_pct", label: _t("Utilisation"), suffix: "%",
              kpi: kpis.utilization_pct },
            { key: "downtime_pct", label: _t("Downtime"), suffix: "%",
              kpi: kpis.downtime_pct },
            { key: "oee_pct", label: _t("OEE"), suffix: "%",
              kpi: kpis.oee_pct },
            { key: "backlog_qty", label: _t("Backlog"), suffix: "",
              kpi: kpis.backlog_qty },
            { key: "pm_due_count", label: _t("PM Due"), suffix: "",
              kpi: kpis.pm_due_count },
        ];
    }

    /** "On target" / "below target" styling for a KPI tile — kept out of
     * the template, which cannot express a raw `<` inside an attribute
     * value without XML-escaping it into illegibility. */
    kpiStatusClass(kpi) {
        if (!kpi.target) {
            return "";
        }
        const onTarget = kpi.higher_is_better
            ? kpi.value >= kpi.target
            : kpi.value <= kpi.target;
        return onTarget ? "fmes-kpi-ok" : "fmes-kpi-warn";
    }

    // ------------------------------------------------------------------
    // Drill-through
    // ------------------------------------------------------------------
    _baseDomain(extra) {
        const domain = [
            ["date", ">=", this.state.dateFrom],
            ["date", "<=", this.state.dateTo],
        ];
        if (this.state.departmentIds && this.state.departmentIds.length) {
            domain.push(["department_id", "in", this.state.departmentIds]);
        }
        return domain.concat(extra || []);
    }

    drillTo(resModel, extra, name, dateField) {
        const domain = this._baseDomain(extra);
        if (dateField && dateField !== "date") {
            domain[0] = [dateField, ">=", this.state.dateFrom];
            domain[1] = [dateField, "<=", this.state.dateTo];
        }
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
    renderCharts() {
        this._destroyCharts();
        const data = this.state.data;
        if (!data) {
            return;
        }
        this._renderProductionTrend(data.production_trend);
        this._renderDowntimePareto(data.downtime_pareto);
        this._renderDepartmentPerformance(data.department_performance);
        this._renderShiftPerformance(data.shift_performance);
        this._renderMachineRanking(data.machine_utilization_ranking);
        this._renderBacklogAgeing(data.backlog_ageing);
        this._renderProductivity(data.productivity_trend);
    }

    _destroyCharts() {
        for (const chart of Object.values(this.charts)) {
            chart.destroy();
        }
        this.charts = {};
    }

    _renderProductionTrend(rows) {
        const el = this.productionTrendRef.el;
        if (!el || !rows) return;
        this.charts.productionTrend = new Chart(el, {
            type: "line",
            data: {
                labels: rows.map((r) => r.date),
                datasets: [
                    {
                        label: _t("Planned"),
                        data: rows.map((r) => r.planned_qty),
                        borderColor: CHART_COLORS.target,
                        fill: false,
                    },
                    {
                        label: _t("Actual"),
                        data: rows.map((r) => r.actual_qty),
                        borderColor: CHART_COLORS.achievement,
                        fill: false,
                    },
                ],
            },
            options: { responsive: true, maintainAspectRatio: false },
        });
    }

    _renderDowntimePareto(rows) {
        const el = this.downtimeParetoRef.el;
        if (!el || !rows) return;
        this.charts.downtimePareto = new Chart(el, {
            data: {
                labels: rows.map((r) => r.reason),
                datasets: [
                    {
                        type: "bar",
                        label: _t("Hours"),
                        data: rows.map((r) => r.hours),
                        backgroundColor: CHART_COLORS.danger,
                        yAxisID: "hours",
                    },
                    {
                        type: "line",
                        label: _t("Cumulative %"),
                        data: rows.map((r) => r.cumulative_pct),
                        borderColor: CHART_COLORS.target,
                        yAxisID: "pct",
                        fill: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    hours: { type: "linear", position: "left" },
                    pct: {
                        type: "linear", position: "right", min: 0, max: 100,
                        grid: { drawOnChartArea: false },
                    },
                },
                onClick: (_ev, elements) => {
                    if (elements.length) {
                        const row = rows[elements[0].index];
                        this.drillTo(
                            "fmes.downtime.report",
                            [["loss_id.name", "=", row.reason]],
                            row.reason);
                    }
                },
            },
        });
    }

    _renderDepartmentPerformance(rows) {
        const el = this.departmentPerfRef.el;
        if (!el || !rows) return;
        this.charts.departmentPerf = new Chart(el, {
            type: "bar",
            data: {
                labels: rows.map((r) => r.department),
                datasets: [{
                    label: _t("Achievement %"),
                    data: rows.map((r) => r.achievement_pct),
                    backgroundColor: CHART_COLORS.achievement,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                onClick: (_ev, elements) => {
                    if (elements.length) {
                        const row = rows[elements[0].index];
                        this.drillTo(
                            "fmes.production.report",
                            [["department_id.name", "=", row.department]],
                            row.department);
                    }
                },
            },
        });
    }

    _renderShiftPerformance(rows) {
        const el = this.shiftPerfRef.el;
        if (!el || !rows) return;
        this.charts.shiftPerf = new Chart(el, {
            type: "bar",
            data: {
                labels: rows.map((r) => r.shift),
                datasets: [
                    {
                        label: _t("Achievement %"),
                        data: rows.map((r) => r.achievement_pct),
                        backgroundColor: CHART_COLORS.achievement,
                    },
                    {
                        label: _t("Utilisation %"),
                        data: rows.map((r) => r.utilization_pct),
                        backgroundColor: CHART_COLORS.info,
                    },
                ],
            },
            options: { responsive: true, maintainAspectRatio: false },
        });
    }

    _renderMachineRanking(rows) {
        const el = this.machineRankingRef.el;
        if (!el || !rows) return;
        this.charts.machineRanking = new Chart(el, {
            type: "bar",
            data: {
                labels: rows.map((r) => r.machine),
                datasets: [{
                    label: _t("Utilisation %"),
                    data: rows.map((r) => r.utilization_pct),
                    backgroundColor: rows.map((r) => (
                        r.is_under_utilized
                            ? CHART_COLORS.danger : CHART_COLORS.success)),
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
                            [["workcenter_id.display_name", "=", row.machine]],
                            row.machine);
                    }
                },
            },
        });
    }

    _renderBacklogAgeing(rows) {
        const el = this.backlogAgeingRef.el;
        if (!el || !rows) return;
        const colors = { "0-3": CHART_COLORS.success, "4-7": CHART_COLORS.warning,
            "8-15": CHART_COLORS.warning, "15+": CHART_COLORS.danger };
        this.charts.backlogAgeing = new Chart(el, {
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

    _renderProductivity(rows) {
        const el = this.productivityRef.el;
        if (!el || !rows) return;
        this.charts.productivity = new Chart(el, {
            type: "line",
            data: {
                labels: rows.map((r) => r.date),
                datasets: [{
                    label: _t("Units / Manpower-Hour"),
                    data: rows.map((r) => r.units_per_manpower_hour),
                    borderColor: CHART_COLORS.achievement,
                    fill: false,
                }],
            },
            options: { responsive: true, maintainAspectRatio: false },
        });
    }
}

registry.category("actions").add(
    "fmes_executive_dashboard", FmesExecutiveDashboard);
