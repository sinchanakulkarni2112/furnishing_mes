/** @odoo-module **/

import { registry } from "@web/core/registry";

/* eslint-disable no-undef */

registry.category("web_tour.tours").add("fmes_shopfloor_terminal_tour", {
    url: "/odoo?debug=assets",
    steps: () => [
        {
            trigger: ".o_fmes_terminal",
            content: "Furnishing MES Shop Floor Terminal",
            run: "next",
        },
        {
            trigger: ".o_fmes_pin_modal",
            content: "Operator PIN gate shown before recording",
            run: "next",
        },
        {
            trigger: ".o_fmes_machine_grid",
            content: "Machines available for this operator",
            run: "next",
        },
        {
            trigger: ".o_fmes_machine_card",
            content: "Select a machine to begin work",
            run: "next",
        },
    ],
});

registry.category("web_tour.tours").add("fmes_scheduling_board_tour", {
    url: "/odoo?debug=assets",
    steps: () => [
        {
            trigger: ".o_fmes_board",
            content: "Scheduling Board overview",
            run: "next",
        },
        {
            trigger: ".o_fmes_board_toolbar",
            content: "Board filters and presets",
            run: "next",
        },
        {
            trigger: ".o_fmes_board_grid",
            content: "Workcenter slots and load",
            run: "next",
        },
    ],
});

registry.category("web_tour.tours").add("fmes_executive_dashboard_tour", {
    url: "/odoo?debug=assets",
    steps: () => [
        {
            trigger: ".o_fmes_dashboard",
            content: "Executive Dashboard",
            run: "next",
        },
        {
            trigger: ".o_fmes_kpi_row",
            content: "Key performance indicators",
            run: "next",
        },
        {
            trigger: ".o_fmes_chart_grid",
            content: "Trends and charts",
            run: "next",
        },
    ],
});
