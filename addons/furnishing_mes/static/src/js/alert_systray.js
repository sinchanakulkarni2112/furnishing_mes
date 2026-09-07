/** @odoo-module **/
/**
 * Alert Center unread-count systray icon (Requirement 10, deliverable 6).
 *
 * Deliberately dumb: it only asks `fmes.alert.get_unread_count()` for a
 * number and opens the Alert Center action on click. All the real logic
 * (what counts as unread, scope, dedup) lives server-side in
 * `fmes.alert` / `fmes.alert.engine` so this widget can never drift from
 * what the list view itself would show.
 */

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const POLL_INTERVAL_MS = 60000;

export class FmesAlertSystray extends Component {
    static template = "furnishing_mes.AlertSystray";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ count: 0 });

        onWillStart(() => this._refreshCount());

        this.pollId = setInterval(() => this._refreshCount(), POLL_INTERVAL_MS);
        onWillUnmount(() => clearInterval(this.pollId));
    }

    async _refreshCount() {
        this.state.count = await this.orm.call("fmes.alert", "get_unread_count", []);
    }

    onClick() {
        this.action.doAction("furnishing_mes.action_fmes_alert");
    }
}

registry.category("systray").add(
    "furnishing_mes.AlertSystray",
    { Component: FmesAlertSystray },
    { sequence: 20 }
);
