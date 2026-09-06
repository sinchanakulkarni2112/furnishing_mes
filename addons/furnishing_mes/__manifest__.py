# -*- coding: utf-8 -*-
{
    'name': 'Furnishing MES',
    'version': '18.0.1.0.0',
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

        # Views and menus
        'views/menus.xml',
    ],

    'demo': [
        # Mock ERP dataset arrives in Phase 2.
    ],

    'assets': {
        # OWL components arrive in Phase 3 (scheduling board), Phase 4
        # (shop-floor terminal) and Phase 10 (executive dashboard).
    },

    'images': ['static/description/icon.png'],
    'application': True,
    'installable': True,
    'auto_install': False,
}
