/** @odoo-module **/

/**
 * Touch-first tile dashboard behind the Furnishing MES top-level menus.
 *
 * Every top-level menu under `furnishing_mes.menu_fmes_root` that has children
 * carries the client action registered at the bottom of this file (assigned in
 * `views/fmes_menus.xml`), and the template extensions in
 * `static/src/xml/menu_dashboard.xml` drop the desktop tab bar entirely while
 * that app is on show — on a shop-floor tablet a dropdown entry is a
 * precision target, a row of tiles is not.
 *
 * The tiles are the children of the menu that is on show, read from the very
 * payload the NavBar renders (`@web/webclient/menus/menu_service`), so a tile
 * can never offer a screen the current user is not allowed to open — menus are
 * already filtered by groups and by model read access before they reach it.
 * Clicking a tile that is a folder — or that carries this dashboard's own
 * action — only moves the component's state, so drilling never swaps the
 * action out from under the component; `doAction` is reserved for leaf tiles
 * that open a real screen.
 *
 * Which menu is on show lives in sessionStorage: the menu service only ever
 * persists the APP it is on (its `menu_id` key holds an app id), never which
 * tab inside the app was selected, and the dashboard component is remounted by
 * the ActionContainer on every action (its `t-key` is a per-action counter),
 * so `setup()` is where the remembered menu is picked up again.
 */

import { Component, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
// Side effect only: the menu service has to have registered itself before
// this module wraps its `start`, whatever order the bundle lists them in.
import "@web/webclient/menus/menu_service";

/** The app menu this dashboard belongs to, and its "home" screen. */
const FMES_ROOT_MENU_XMLID = "furnishing_mes.menu_fmes_root";
/** The menu whose screens the dashboard should show when it next mounts. */
const ACTIVE_MENU_STORAGE_KEY = "fmes_menu_dashboard.active_menu_id";
/** The tag this file registers the dashboard component under. */
const DASHBOARD_ACTION_TAG = "fmes_menu_dashboard";

/**
 * Whether `menu` is a direct child of the Furnishing MES app, i.e. one of the
 * tabs the dashboard stands in for. Decided from the payload (`appID` plus the
 * app's own `children`) rather than a hard-coded list of ids, so a tab added
 * later needs no change here.
 */
function isFmesTab(menuService, menu) {
    if (!menu || !menu.appID) {
        return false;
    }
    const app = menuService.getMenu(menu.appID);
    return Boolean(app && app.xmlid === FMES_ROOT_MENU_XMLID && app.children.includes(menu.id));
}

/**
 * Remember the menu the dashboard should show. Selecting the app itself
 * forgets it, so the tab overview — the app's home screen — is what opens.
 */
function storeActiveMenu(menuService, menu) {
    const selected = typeof menu === "number" ? menuService.getMenu(menu) : menu;
    if (!selected) {
        return;
    }
    if (selected.xmlid === FMES_ROOT_MENU_XMLID) {
        browser.sessionStorage.removeItem(ACTIVE_MENU_STORAGE_KEY);
    } else if (selected.children && selected.children.length && isFmesTab(menuService, selected)) {
        browser.sessionStorage.setItem(ACTIVE_MENU_STORAGE_KEY, String(selected.id));
    }
}

// Every route into a menu goes through `menuService.selectMenu` — the navbar's
// desktop tabs and sidebar, the overflow menu, the command palette, the app
// tile and the webclient's own default-app call on login — so the service is
// wrapped once here instead of each of those callers being patched. This runs
// while the bundle is being evaluated, i.e. before the webclient starts its
// services.
const menuServiceDefinition = registry.category("services").get("menu");
const startMenuService = menuServiceDefinition.start;
menuServiceDefinition.start = async function (...args) {
    const menuService = await startMenuService.apply(this, args);
    const selectMenu = menuService.selectMenu;
    menuService.selectMenu = function (menu) {
        storeActiveMenu(menuService, menu);
        return selectMenu.call(this, menu);
    };
    return menuService;
};

export class MenuDashboard extends Component {
    static template = "furnishing_mes.MenuDashboard";
    static props = ["*"];

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.state = useState({ menuId: this.initialMenuId() });
    }

    /**
     * The menu remembered by the last selection, else the Furnishing MES app
     * itself — the home overview. Nothing else can ever be in the key: only
     * a tab of this app is ever written there, so a dashboard opened from
     * another application cannot show its sections.
     */
    initialMenuId() {
        const storedId = Number(browser.sessionStorage.getItem(ACTIVE_MENU_STORAGE_KEY));
        if (storedId && this.menuService.getMenu(storedId)) {
            return storedId;
        }
        const app = this.menuService
            .getApps()
            .find((candidate) => candidate.xmlid === FMES_ROOT_MENU_XMLID);
        return app ? app.id : null;
    }

    get menu() {
        return (this.state.menuId && this.menuService.getMenu(this.state.menuId)) || null;
    }

    get title() {
        return this.menu ? this.menu.name : "";
    }

    get tiles() {
        if (!this.menu) {
            return [];
        }
        return this.menu.children
            .map((menuId) => this.menuService.getMenu(menuId))
            .filter(Boolean);
    }

    get canGoBack() {
        return Boolean(this.menu && this.menu.appID && this.menu.id !== this.menu.appID);
    }

    goBack() {
        const current = this.menu;
        if (!current) {
            return;
        }
        // The payload carries no parent id, so the parent is the menu that
        // lists this one among its children. Only reachable from a menu below
        // the app, and the app itself is never a child of anything a user can
        // drill back to.
        const parent = this.menuService
            .getAll()
            .find((menu) => menu.children && menu.children.includes(current.id));
        if (parent) {
            this.remember(parent.id);
        }
    }

    /**
     * A tile is either another step of the dashboard — anything with children,
     * and anything carrying this dashboard's own action, which is what every
     * top-level tab resolves to — or a leaf that opens a real screen. The
     * first case only moves the component's state, so the tiles re-render in
     * place and the Back button can walk straight back up; running doAction
     * for it would replace this component with a fresh one and lose the drill.
     */
    async onTileClick(tile) {
        if (tile.children && tile.children.length) {
            this.remember(tile.id);
            return;
        }
        if (!tile.actionID) {
            return;
        }
        if (tile.actionModel === "ir.actions.client") {
            // Client actions are the only ones that can BE this dashboard, so
            // they are resolved before being opened; an act_window tile
            // (Support Tickets, any native view) is a leaf by construction and
            // costs no extra call.
            const action = await this.actionService.loadAction(tile.actionID);
            if (action && action.tag === DASHBOARD_ACTION_TAG) {
                this.remember(tile.id);
                return;
            }
            await this.actionService.doAction(action, { clearBreadcrumbs: true });
            return;
        }
        await this.actionService.doAction(tile.actionID, { clearBreadcrumbs: true });
    }

    remember(menuId) {
        this.state.menuId = menuId;
        browser.sessionStorage.setItem(ACTIVE_MENU_STORAGE_KEY, String(menuId));
    }
}

registry.category("actions").add("fmes_menu_dashboard", MenuDashboard);

patch(NavBar.prototype, {
    /**
     * Used by the SectionsMenu extension to drop the tab bar entirely while
     * the Furnishing MES app is on show — its screens are reached through the
     * tiles, not through tabs.
     */
    isFmesApp() {
        const app = this.menuService.getCurrentApp();
        return Boolean(app && app.xmlid === FMES_ROOT_MENU_XMLID);
    },
    /**
     * Used by the mobile sidebar template inheritance to spot the tabs that
     * have to become dashboard entries instead of expandable folders.
     */
    isFmesMenuDashboardTab(menu) {
        return isFmesTab(this.menuService, menu);
    },
});
