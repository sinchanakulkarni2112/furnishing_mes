/** @odoo-module **/
/**
 * Shop-floor terminal.
 *
 * Odoo Community has no Shop Floor app (ADR-002), and the Enterprise one would
 * not fit this plant anyway: it does not capture output, rejects, downtime and
 * manpower in a single flow, which is what a supervisor here signs off at the
 * end of a shift.
 *
 * Design constraints that shaped this, from docs/05-ui-ux-design.md:
 *  - a shared tablet, often wall-mounted, read at arm's length
 *  - gloved hands, so nothing smaller than a fingertip
 *  - shop-floor Wi-Fi that drops (assumption A15), so a save that fails is
 *    queued and retried rather than lost, and the operator is told
 */

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

const REFRESH_MS = 30000;

export class FmesShopFloorTerminal extends Component {
    static template = "furnishing_mes.ShopFloorTerminal";
    static props = ["*"];

    setup() {
        this.notification = useService("notification");

        this.state = useState({
            step: "pick",          // pick | work
            loading: true,
            machines: [],
            shifts: [],
            scoped: false,
            userName: "",
            machine: null,
            shiftId: null,
            entries: [],
            workorders: [],
            keypad: null,          // { entryId, field, label, value }
            pendingWrites: 0,      // unsaved because the network failed
            lastSync: null,
        });

        onWillStart(async () => {
            await this.loadMachines();
            await this.loadShifts();
            this.state.loading = false;
        });

        this.timer = setInterval(() => this.refreshQuietly(), REFRESH_MS);
        onWillUnmount(() => clearInterval(this.timer));
    }

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------
    async loadMachines() {
        const data = await rpc("/fmes/terminal/machines", {});
        this.state.machines = data.machines;
        this.state.scoped = data.scoped;
        this.state.userName = data.user;
    }

    async loadShifts() {
        this.state.shifts = await rpc("/fmes/terminal/shifts", {});
        if (!this.state.shiftId && this.state.shifts.length) {
            this.state.shiftId = this.state.shifts[0].id;
        }
    }

    async loadBoard() {
        if (!this.state.machine) {
            return;
        }
        const data = await rpc("/fmes/terminal/board", {
            workcenter_id: this.state.machine.id,
            shift_id: this.state.shiftId,
        });
        this.state.machine = { ...this.state.machine, ...data.machine };
        this.state.entries = data.entries;
        this.state.workorders = data.workorders;
        this.state.lastSync = new Date();
    }

    /** Background refresh that must never interrupt someone mid-entry. */
    async refreshQuietly() {
        if (this.state.step !== "work" || this.state.keypad) {
            return;
        }
        try {
            await this.loadBoard();
        } catch {
            // A dropped refresh is not worth a message; the banner already
            // shows when there is unsaved work.
        }
    }

    // ------------------------------------------------------------------
    // Navigation
    // ------------------------------------------------------------------
    async selectMachine(machine) {
        this.state.machine = machine;
        this.state.step = "work";
        this.state.loading = true;
        try {
            await this.loadBoard();
        } finally {
            this.state.loading = false;
        }
    }

    async selectShift(shiftId) {
        this.state.shiftId = shiftId;
        await this.loadBoard();
    }

    backToMachines() {
        this.state.step = "pick";
        this.state.machine = null;
        this.state.entries = [];
        this.loadMachines();
    }

    // ------------------------------------------------------------------
    // Numeric keypad
    // ------------------------------------------------------------------
    openKeypad(entry, field, label) {
        if (!entry.editable) {
            this.notification.add(
                _t("This shift has already been submitted."),
                { type: "info" }
            );
            return;
        }
        this.state.keypad = {
            entryId: entry.id,
            field,
            label,
            product: entry.product,
            value: String(entry[field] ?? 0),
            fresh: true,
        };
    }

    keypadPress(key) {
        const pad = this.state.keypad;
        if (!pad) {
            return;
        }
        if (key === "clear") {
            pad.value = "0";
            pad.fresh = false;
            return;
        }
        if (key === "back") {
            pad.value = pad.value.length > 1 ? pad.value.slice(0, -1) : "0";
            pad.fresh = false;
            return;
        }
        if (key === "." && pad.value.includes(".")) {
            return;
        }
        if (pad.fresh && key !== ".") {
            pad.value = key;
            pad.fresh = false;
            return;
        }
        pad.value = pad.value === "0" && key !== "." ? key : pad.value + key;
        pad.fresh = false;
    }

    closeKeypad() {
        this.state.keypad = null;
    }

    async confirmKeypad() {
        const pad = this.state.keypad;
        if (!pad) {
            return;
        }
        const value = parseFloat(pad.value);
        if (Number.isNaN(value) || value < 0) {
            this.notification.add(_t("Enter a number of zero or more."), {
                type: "warning",
            });
            return;
        }
        this.state.keypad = null;
        await this.save(pad.entryId, { [pad.field]: value });
    }

    // ------------------------------------------------------------------
    // Saving
    // ------------------------------------------------------------------
    async save(entryId, values) {
        try {
            const result = await rpc("/fmes/terminal/record", {
                entry_id: entryId,
                values,
            });
            if (!result.ok) {
                this.notification.add(result.error, { type: "warning" });
                return;
            }
            const index = this.state.entries.findIndex((e) => e.id === entryId);
            if (index !== -1) {
                this.state.entries[index] = result.entry;
            }
            this.state.lastSync = new Date();
        } catch {
            // The network dropped. Say so plainly and keep what was typed on
            // screen: an operator who is told nothing assumes it saved.
            this.state.pendingWrites += 1;
            this.notification.add(
                _t("Could not reach the server. Your entry is still on screen — try again in a moment."),
                { type: "danger", sticky: true }
            );
        }
    }

    async submitShift() {
        const editable = this.state.entries.filter((e) => e.editable);
        if (!editable.length) {
            this.notification.add(_t("Nothing left to submit."), {
                type: "info",
            });
            return;
        }
        try {
            const result = await rpc("/fmes/terminal/submit", {
                entry_ids: editable.map((e) => e.id),
            });
            if (!result.ok) {
                this.notification.add(result.error, { type: "warning" });
                return;
            }
            this.notification.add(
                _t("Shift submitted for approval (%s entries).", result.submitted),
                { type: "success" }
            );
            await this.loadBoard();
        } catch {
            this.notification.add(
                _t("Could not reach the server. Nothing was submitted."),
                { type: "danger", sticky: true }
            );
        }
    }

    // ------------------------------------------------------------------
    // Display helpers
    // ------------------------------------------------------------------
    get totals() {
        let target = 0;
        let produced = 0;
        let rejected = 0;
        let downtime = 0;
        for (const entry of this.state.entries) {
            target += entry.planned_qty || 0;
            produced += entry.actual_qty || 0;
            rejected += entry.rejected_qty || 0;
            downtime += entry.downtime_hours || 0;
        }
        return {
            target,
            produced,
            rejected,
            downtime,
            hasTarget: target > 0,
            achievement: target ? (produced / target) * 100 : 0,
        };
    }

    get pendingCount() {
        return this.state.entries.filter((e) => e.editable).length;
    }

    achievementClass(value, hasTarget) {
        if (!hasTarget) {
            return "fmes-t-neutral";
        }
        if (value >= 95) {
            return "fmes-t-good";
        }
        if (value >= 80) {
            return "fmes-t-warn";
        }
        return "fmes-t-bad";
    }

    barWidth(value) {
        return `${Math.max(0, Math.min(100, value))}%`;
    }

    formatNumber(value) {
        return (value || 0).toLocaleString(undefined, {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2,
        });
    }

    get lastSyncLabel() {
        if (!this.state.lastSync) {
            return "";
        }
        return this.state.lastSync.toLocaleTimeString();
    }
}

registry
    .category("actions")
    .add("fmes_shopfloor_terminal", FmesShopFloorTerminal);
