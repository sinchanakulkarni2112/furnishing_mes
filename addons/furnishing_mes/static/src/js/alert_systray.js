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
        this.isDestroyed = false;

        onWillStart(() => this._refreshCount());

        this.pollId = setInterval(() => this._refreshCount(), POLL_INTERVAL_MS);
        onWillUnmount(() => {
            this.isDestroyed = true;
            clearInterval(this.pollId);
        });
    }

    async _refreshCount() {
        // The navbar (and this systray item with it) can be torn down while
        // this call is still in flight — e.g. the webclient re-rendering
        // during initial boot. Writing to `state` on a destroyed component
        // throws and, left unhandled here, can abort the whole app's mount.
        const count = await this.orm.call("fmes.alert", "get_unread_count", []);
        if (!this.isDestroyed) {
            this.state.count = count;
        }
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
