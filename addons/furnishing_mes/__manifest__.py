# -*- coding: utf-8 -*-
{
    'name': 'Furnishing MES',
    'version': '18.0.10.0.0',
    'category': 'Manufacturing/Manufacturing',
    'summary': 'Manufacturing Execution System for furnishing production',
    'description': """
Furnishing MES
==============

A Manufacturing Execution System for a furnishing manufacturer, built on
Odoo 18 Community.

Replaces manual Excel-based production planning with:

* capacity-aware automated production planning (machine-wise, shift-wise)
* daily production targets and actual output tracking
* a touch-first shop-floor terminal for operators
* digital downtime capture and loss-reason analysis
* machine utilisation and OEE monitoring
* preventive and breakdown maintenance management
* manpower deployment and utilisation tracking
* backlog and carry-forward order management
* management dashboards and an automated reporting suite
* a customer self-service portal

The module extends Odoo's native Manufacturing and Maintenance apps rather
than duplicating them, so native OEE, MTBF and MTTR computations stay correct.

ERP 10.8 integration is deferred; the integration seam is present but dormant.
""",
    'author': 'Sinchana Kulkarni',
    'maintainer': 'Sinchana Kulkarni',
    'website': 'https://github.com/sinchanakulkarni2112/furnishing_mes',
    'license': 'LGPL-3',

    # Every dependency below was verified to exist in Odoo 18.0 Community.
    # See docs/13-odoo-edition-constraints.md for the audit.
    'depends': [
        'base',
        'mail',                    # chatter, activities, templates, tracking
        'web',
        'product',
        'uom',
        'stock',
        'resource',                # working calendars behind shift capacity
        'mrp',                     # work centers, work orders, productivity losses, OEE
        'maintenance',             # equipment, requests, MTBF / MTTR
        'hr',                      # employees and departments
        'sale_management',         # mock sales orders standing in for ERP 10.8
        'portal',                  # customer self-service
        'base_automation',         # rule-driven triggers for alerts
        'base_import',             # CSV / XLSX import
        'spreadsheet_dashboard',   # management self-service dashboards
    ],

    'data': [
        # Security must load before anything that references a group.
        'security/fmes_groups.xml',
        'security/ir.model.access.csv',
        'security/fmes_record_rules.xml',

        # Configuration data
        'data/fmes_sequences.xml',
        'data/fmes_loss_reasons.xml',
        'data/fmes_maintenance_team.xml',
        'data/fmes_crons.xml',

        # Views, then menus (menus reference the actions above)
        'views/fmes_shift_views.xml',
        'views/fmes_capacity_matrix_views.xml',
        'views/fmes_production_plan_views.xml',
        'views/fmes_production_entry_views.xml',
        'views/fmes_production_entry_downtime_views.xml',
        'views/fmes_live_status_views.xml',
        'views/res_users_views.xml',
        'views/mrp_workcenter_views.xml',
        'views/mrp_workcenter_productivity_views.xml',
        'views/maintenance_equipment_views.xml',
        'views/fmes_utilization_report_views.xml',
        'views/mrp_workcenter_utilization_views.xml',
        'views/fmes_maintenance_schedule_views.xml',
        'views/maintenance_request_views.xml',
        'views/fmes_maintenance_report_views.xml',
        'views/fmes_manpower_log_views.xml',
        'views/fmes_operator_allocation_views.xml',
        'views/fmes_manpower_impact_report_views.xml',
        'views/mrp_production_views.xml',
        'views/fmes_backlog_snapshot_views.xml',
        'views/fmes_production_report_views.xml',
        'views/fmes_executive_dashboard_views.xml',
        'views/menus.xml',
    ],

    'demo': [
        # Mock plant dataset standing in for ERP 10.8 (Requirement 11,
        # deferred). Loaded only when demo data is enabled, never in
        # production.
        'demo/fmes_demo_masters.xml',
        'demo/fmes_demo_products.xml',
        'demo/fmes_demo_capacity.xml',
        'demo/fmes_demo_orders.xml',
        'demo/fmes_demo_maintenance.xml',
        'demo/fmes_demo_manpower.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'furnishing_mes/static/src/scss/fmes_board.scss',
            'furnishing_mes/static/src/scss/fmes_terminal.scss',
            'furnishing_mes/static/src/scss/fmes_dashboard.scss',
            'furnishing_mes/static/src/js/scheduling_board.js',
            'furnishing_mes/static/src/js/shopfloor_terminal.js',
            'furnishing_mes/static/src/js/executive_dashboard.js',
            'furnishing_mes/static/src/xml/scheduling_board.xml',
            'furnishing_mes/static/src/xml/shopfloor_terminal.xml',
            'furnishing_mes/static/src/xml/executive_dashboard.xml',
        ],
    },

    'images': ['static/description/icon.png'],
    'application': True,
    'installable': True,
    'auto_install': False,
}
