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
            downtimeReasons: [],   // grouped by category, loaded once
            downtimeModal: null,   // { entry, step: 'reasons'|'remark', reason }
            now: Date.now(),       // ticks every second, drives the running timer
            productPicker: null,   // { products, loading, selected, materialCheck }
            materialModal: null,   // { product, result } — on-demand check for a planned entry
            submitConfirm: null,   // { editableCount } — asks about downtime before submitting
            postSubmitPicker: null, // { entries } — "which product had downtime?" when more than one
        });

        onWillStart(async () => {
            await this.loadMachines();
            await this.loadShifts();
            await this.loadDowntimeReasons();
            this.state.loading = false;
        });

        this.timer = setInterval(() => this.refreshQuietly(), REFRESH_MS);
        this.tickTimer = setInterval(() => {
            this.state.now = Date.now();
        }, 1000);
        onWillUnmount(() => {
            clearInterval(this.timer);
            clearInterval(this.tickTimer);
        });
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

    async loadDowntimeReasons() {
        this.state.downtimeReasons = await rpc(
            "/fmes/terminal/downtime/reasons", {});
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
    // Add product — manual entry creation, with a live material check
    // ------------------------------------------------------------------
    async openProductPicker() {
        this.state.productPicker = { products: [], loading: true,
                                      selected: null, materialCheck: null };
        try {
            const products = await rpc("/fmes/terminal/products", {
                workcenter_id: this.state.machine.id,
            });
            this.state.productPicker.products = products;
        } finally {
            this.state.productPicker.loading = false;
        }
    }

    closeProductPicker() {
        this.state.productPicker = null;
    }

    async pickProduct(product) {
        const picker = this.state.productPicker;
        if (!picker) {
            return;
        }
        picker.selected = product;
        picker.materialCheck = null;
        // Checked against one unit at pick time — the entry does not exist
        // yet to have a real target quantity. It is a directional signal
        // ("is there anything of this in stock at all"), not a promise;
        // the entry's own material check (once created) is the precise one.
        picker.materialCheck = await rpc("/fmes/terminal/material_check", {
            product_id: product.id,
            qty: 1,
        });
    }

    async confirmAddProduct() {
        const picker = this.state.productPicker;
        if (!picker || !picker.selected) {
            return;
        }
        try {
            const result = await rpc("/fmes/terminal/create_entry", {
                workcenter_id: this.state.machine.id,
                shift_id: this.state.shiftId,
                product_id: picker.selected.id,
            });
            if (!result.ok) {
                this.notification.add(result.error, { type: "warning" });
                return;
            }
            this.state.entries.push(result.entry);
            this.state.productPicker = null;
        } catch {
            this.notification.add(
                _t("Could not reach the server. The product was not added — try again."),
                { type: "danger", sticky: true });
        }
    }

    /** On-demand check for an already-planned entry, against its real target. */
    async checkEntryMaterials(entry) {
        this.state.materialModal = { product: entry.product, result: null };
        this.state.materialModal.result = await rpc(
            "/fmes/terminal/material_check", {
                product_id: entry.product_id,
                qty: entry.planned_qty || 1,
            });
    }

    closeMaterialModal() {
        this.state.materialModal = null;
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
    // Downtime — reason picker and running timer
    // ------------------------------------------------------------------
    runningEventFor(entry) {
        return entry.downtime_events.find((ev) => ev.running) || null;
    }

    elapsedLabel(dateStartIso) {
        // date_start comes back as a naive UTC string ("YYYY-MM-DD HH:MM:SS");
        // append Z so the browser parses it as UTC rather than local time.
        const start = new Date(dateStartIso.replace(" ", "T") + "Z").getTime();
        const seconds = Math.max(0, Math.floor((this.state.now - start) / 1000));
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        const pad = (n) => String(n).padStart(2, "0");
        return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
    }

    openDowntimeReasons(entry) {
        if (this.runningEventFor(entry)) {
            // A running timer opens straight to "stop", not the reason grid.
            return;
        }
        this.state.downtimeModal = { entry, step: "reasons", reason: null,
                                     remarks: "" };
    }

    pickDowntimeReason(reason) {
        const modal = this.state.downtimeModal;
        if (!modal) {
            return;
        }
        if (reason.requires_remark) {
            // "Other" needs a remark before the server will accept it at
            // all (the model itself refuses to save one without a note), so
            // ask for it now rather than letting the start call fail.
            modal.step = "remark";
            modal.reason = reason;
            return;
        }
        this.startDowntime(modal.entry, reason.id, "");
    }

    async confirmDowntimeRemark() {
        const modal = this.state.downtimeModal;
        if (!modal || !modal.reason) {
            return;
        }
        if (!modal.remarks.trim()) {
            this.notification.add(
                _t("A note is required for 'Other'."), { type: "warning" });
            return;
        }
        await this.startDowntime(modal.entry, modal.reason.id, modal.remarks);
    }

    closeDowntimeModal() {
        this.state.downtimeModal = null;
    }

    async startDowntime(entry, lossId, remarks) {
        try {
            const result = await rpc("/fmes/terminal/downtime/start", {
                entry_id: entry.id,
                loss_id: lossId,
                remarks: remarks || null,
            });
            if (!result.ok) {
                this.notification.add(result.error, { type: "warning" });
                return;
            }
            this.applyEntryUpdate(result.entry);
            this.state.downtimeModal = null;
        } catch {
            this.notification.add(
                _t("Could not reach the server. Downtime was not logged — try again."),
                { type: "danger", sticky: true });
        }
    }

    async stopDowntime(entry, event) {
        try {
            const result = await rpc("/fmes/terminal/downtime/stop", {
                event_id: event.id,
            });
            if (!result.ok) {
                this.notification.add(result.error, { type: "warning" });
                return;
            }
            if (result.entry) {
                this.applyEntryUpdate(result.entry);
            }
        } catch {
            this.notification.add(
                _t("Could not reach the server. The timer is still running — try again."),
                { type: "danger", sticky: true });
        }
    }

    applyEntryUpdate(entry) {
        const index = this.state.entries.findIndex((e) => e.id === entry.id);
        if (index !== -1) {
            this.state.entries[index] = entry;
        }
        this.state.lastSync = new Date();
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
            this.applyEntryUpdate(result.entry);
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

    submitShift() {
        const editable = this.state.entries.filter((e) => e.editable);
        if (!editable.length) {
            this.notification.add(_t("Nothing left to submit."), {
                type: "info",
            });
            return;
        }
        // Ask before submitting, not after: the answer decides what happens
        // right after the submit call resolves (straight back to the
        // machine list, or into the downtime reason picker), so it has to
        // be known first.
        this.state.submitConfirm = { editableCount: editable.length };
    }

    cancelSubmit() {
        this.state.submitConfirm = null;
    }

    async answerSubmit(hadDowntime) {
        const editable = this.state.entries.filter((e) => e.editable);
        this.state.submitConfirm = null;

        if (hadDowntime) {
            // The server refuses to submit an entry that reports neither
            // production nor downtime (fmes_production_entry.action_submit)
            // — and a downtime timer only counts toward downtime_hours once
            // it is STOPPED, not the moment it starts (see
            // _fmes_recompute_downtime_hours). So if nothing has been
            // recorded on ANY entry yet, submitting now would just bounce
            // off that rule. Log the downtime first in that case, and let
            // the operator tap Submit again once it is stopped — output
            // already on the entries (a partial shift with SOME downtime)
            // submits immediately as normal, then opens the logger after,
            // matching the usual order.
            const nothingRecordedYet = editable.every(
                (e) => e.actual_qty <= 0 && e.downtime_hours <= 0);
            if (nothingRecordedYet) {
                this.notification.add(
                    _t("Log the downtime, then tap Submit shift again once it's stopped."),
                    { type: "info" });
                if (editable.length === 1) {
                    this.openDowntimeReasons(editable[0]);
                } else {
                    this.state.postSubmitPicker = { entries: editable };
                }
                return;
            }
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
            return;
        }
        if (hadDowntime) {
            // Submitted entries are locked but downtime logging is not
            // gated on entry.editable (see openDowntimeReasons) — an
            // operator can still log what happened on an already-submitted
            // shift. One entry: go straight to the reason grid. More than
            // one: ask which product it was on first.
            if (this.state.entries.length === 1) {
                this.openDowntimeReasons(this.state.entries[0]);
            } else if (this.state.entries.length > 1) {
                this.state.postSubmitPicker = { entries: this.state.entries };
            }
        }
    }

    choosePostSubmitEntry(entry) {
        this.state.postSubmitPicker = null;
        this.openDowntimeReasons(entry);
    }

    closePostSubmitPicker() {
        this.state.postSubmitPicker = null;
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
