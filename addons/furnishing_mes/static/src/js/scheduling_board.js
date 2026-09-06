/** @odoo-module **/
/**
 * Scheduling board.
 *
 * Replaces the Gantt view, which is Odoo Enterprise only (ADR-003). Rather
 * than imitating a generic timeline, this answers the question a planner
 * actually has: which machine-shift slots are overloaded, and what can be
 * moved out of them.
 *
 * Machines run down the page, date-shift slots across it. Every load
 * percentage shown is computed on the server, so what the planner acts on is
 * the same number the planning engine used.
 */

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const DAY_MS = 24 * 60 * 60 * 1000;

function toISO(date) {
    return date.toISOString().slice(0, 10);
}

export class FmesSchedulingBoard extends Component {
    static template = "furnishing_mes.SchedulingBoard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        const params = this.props.action.params || this.props.action.context || {};
        const today = new Date();
        const start = params.date_from
            ? new Date(params.date_from)
            : new Date(today.getTime());
        const end = params.date_to
            ? new Date(params.date_to)
            : new Date(today.getTime() + 6 * DAY_MS);

        this.state = useState({
            dateFrom: toISO(start),
            dateTo: toISO(end),
            planId: params.plan_id || null,
            loading: true,
            data: null,
            dragging: null,
        });

        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "fmes.production.plan",
                "get_board_data",
                [this.state.dateFrom, this.state.dateTo, this.state.planId]
            );
        } finally {
            this.state.loading = false;
        }
    }

    // ------------------------------------------------------------------
    // Derived values
    // ------------------------------------------------------------------
    get columns() {
        const data = this.state.data;
        if (!data) {
            return [];
        }
        const columns = [];
        for (const date of data.dates) {
            for (const shift of data.shifts) {
                columns.push({ date, shift, key: `${date}|${shift.id}` });
            }
        }
        return columns;
    }

    cell(machineId, date, shiftId) {
        const cells = this.state.data ? this.state.data.cells : {};
        return cells[`${machineId}|${date}|${shiftId}`] || null;
    }

    /**
     * Load bands, matching the legend. Colour alone never carries the meaning:
     * the percentage is always printed in the cell as well.
     */
    cellClass(cell) {
        if (!cell || !cell.capacity) {
            return "fmes-cell fmes-cell-none";
        }
        const pct = cell.pct || 0;
        if (pct > 100) {
            return "fmes-cell fmes-cell-over";
        }
        if (pct >= 90) {
            return "fmes-cell fmes-cell-high";
        }
        if (pct >= 60) {
            return "fmes-cell fmes-cell-mid";
        }
        if (pct > 0) {
            return "fmes-cell fmes-cell-low";
        }
        return "fmes-cell fmes-cell-empty";
    }

    cellTitle(machine, column, cell) {
        const header = `${machine.name} — ${column.date} ${column.shift.code}`;
        if (!cell || !cell.lines) {
            const capacity = cell ? cell.capacity.toFixed(2) : "0.00";
            return `${header}\n${_t("Idle")} — ${capacity} h ${_t("available")}`;
        }
        return [
            header,
            `${_t("Planned")}: ${cell.hours.toFixed(2)} h ${_t("of")} ${cell.capacity.toFixed(2)} h (${cell.pct.toFixed(0)}%)`,
            `${_t("Quantity")}: ${cell.qty.toFixed(2)}`,
            `${_t("Lines")}: ${cell.lines}`,
            cell.products.slice(0, 5).join(", "),
        ].join("\n");
    }

    get summary() {
        const data = this.state.data;
        if (!data) {
            return null;
        }
        let planned = 0;
        let capacity = 0;
        let overloaded = 0;
        for (const cell of Object.values(data.cells)) {
            planned += cell.hours || 0;
            capacity += cell.capacity || 0;
            if ((cell.pct || 0) > 100) {
                overloaded += 1;
            }
        }
        return {
            planned: planned.toFixed(1),
            capacity: capacity.toFixed(1),
            pct: capacity ? ((planned / capacity) * 100).toFixed(1) : "0.0",
            overloaded,
            machines: data.machines.length,
        };
    }

    // ------------------------------------------------------------------
    // Interaction
    // ------------------------------------------------------------------
    async onDateChange(field, ev) {
        this.state[field] = ev.target.value;
        await this.load();
    }

    openCell(machine, column, cell) {
        if (!cell || !cell.line_ids.length) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: `${machine.name} — ${column.date} ${column.shift.code}`,
            res_model: "fmes.production.plan.line",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [["id", "in", cell.line_ids]],
        });
    }

    onDragStart(machine, column, cell, ev) {
        if (!cell || !cell.line_ids.length) {
            ev.preventDefault();
            return;
        }
        this.state.dragging = {
            lineIds: cell.line_ids,
            from: `${machine.name} ${column.date} ${column.shift.code}`,
        };
        ev.dataTransfer.effectAllowed = "move";
        // Firefox refuses to start a drag without data on the transfer.
        ev.dataTransfer.setData("text/plain", cell.line_ids.join(","));
    }

    onDragOver(ev) {
        if (this.state.dragging) {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "move";
        }
    }

    async onDrop(machine, column, ev) {
        ev.preventDefault();
        const dragging = this.state.dragging;
        this.state.dragging = null;
        if (!dragging) {
            return;
        }
        const result = await this.orm.call(
            "fmes.production.plan",
            "move_plan_lines",
            [dragging.lineIds, machine.id, column.date, column.shift.id]
        );
        if (result.ok) {
            this.notification.add(
                _t("Moved %s line(s) to %s.", result.moved, machine.name),
                { type: "success" }
            );
            await this.load();
        } else {
            // The server refuses infeasible moves and explains why, rather
            // than letting the board drift out of step with reality.
            this.notification.add(result.error, {
                type: "warning",
                title: _t("Move refused"),
            });
        }
    }

    onDragEnd() {
        this.state.dragging = null;
    }
}

registry.category("actions").add("fmes_scheduling_board", FmesSchedulingBoard);
