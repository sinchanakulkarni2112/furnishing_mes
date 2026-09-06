# 02 — System Architecture

## 1. Architectural Principles

| # | Principle | Rationale |
|---|---|---|
| A1 | **Extend, don't reinvent** | Odoo's `mrp` and `maintenance` apps already model work centers, work orders, productivity losses, equipment and MTBF/MTTR. Building parallel models would fragment the data and break Odoo's native OEE and reporting. |
| A2 | **One installable addon** | Everything ships as `addons/furnishing_mes`. A reviewer installs one module and gets the whole MES. |
| A3 | **Thin views, fat services** | Business rules live in model methods and dedicated `AbstractModel` services (e.g. `fmes.planning.engine`), never in views or controllers. This keeps logic unit-testable and reusable by cron, wizard and API alike. |
| A4 | **Integration seam from day one** | All externally-sourced records carry `erp_external_id` / `erp_sync_state`. Nothing about the domain model changes when ERP 10.8 arrives. |
| A5 | **Read models for analytics** | Dashboards and reports read from PostgreSQL SQL views (`_auto = False` models), never by aggregating in Python. Keeps dashboards fast as history grows. |
| A6 | **Security by record rule, not by view** | Hiding a menu is not access control. Every model gets ACLs plus record rules; the Shop-Floor Terminal is safe even if a URL is guessed. |
| A7 | **Config over code** | Shifts, capacity, loss reasons, alert thresholds are data records, editable by the Plant Manager without a redeploy. |

## 2. Container Topology

```
┌─────────────────────────────────────────────────────────────┐
│  Docker host (on-prem server or developer laptop)           │
│                                                             │
│  ┌───────────────────────────┐   ┌───────────────────────┐  │
│  │  web                      │   │  db                   │  │
│  │  odoo:18.0                │   │  postgres:15          │  │
│  │  :8069  HTTP + longpoll   │──▶│  :5432 (internal)     │  │
│  │                           │   │                       │  │
│  │  volumes:                 │   │  volumes:             │  │
│  │   ./addons  → /mnt/extra- │   │   fmes-db-data        │  │
│  │              addons (ro)  │   │    → /var/lib/         │  │
│  │   ./config  → /etc/odoo   │   │      postgresql/data  │  │
│  │   fmes-web-data           │   │                       │  │
│  │    → /var/lib/odoo        │   │                       │  │
│  └───────────────────────────┘   └───────────────────────┘  │
│              │                                              │
│              └── network: fmes-net (bridge, internal)       │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
              Browser / Tablet on the shop floor
```

**Deliberately excluded:** no React, no FastAPI, no Celery, no Redis, no Nginx in
the standard stack. Odoo's built-in cron (`ir.cron`) replaces Celery; its bundled
Werkzeug server serves the app directly. A reverse proxy is added only for
internet-facing production — see [`08-deployment-operations.md`](08-deployment-operations.md).

### Services

| Service | Image | Ports | Purpose |
|---|---|---|---|
| `web` | `odoo:18.0` | `8069:8069` | Odoo application server, cron workers, web UI |
| `db` | `postgres:15` | internal only | Single source of truth |

Named volumes: `fmes-db-data` (database), `fmes-web-data` (filestore —
attachments, report PDFs, equipment photos).

Bind mounts: `./addons` (our module, live-editable) and `./config/odoo.conf`.

## 3. Application Layers

```
┌──────────────────────────────────────────────────────────────┐
│ PRESENTATION                                                 │
│  Odoo views (list/form/kanban/pivot/graph/calendar/search)   │
│  OWL 2 components: Shop-Floor Terminal · Scheduling Board    │
│                    · Executive Dashboard · Alert Center      │
│  QWeb: PDF reports, portal templates                         │
├──────────────────────────────────────────────────────────────┤
│ ACCESS CONTROL                                               │
│  res.groups · ir.model.access.csv · ir.rule (record rules)   │
│  Portal controllers with explicit ownership checks           │
├──────────────────────────────────────────────────────────────┤
│ SERVICE / DOMAIN                                             │
│  fmes.planning.engine   — capacity-aware plan generation     │
│  fmes.utilization.service — utilisation & OEE computation    │
│  fmes.alert.engine      — rule evaluation & dispatch         │
│  fmes.backlog.service   — snapshot & carry-forward logic     │
│  fmes.report.service    — report dataset assembly            │
├──────────────────────────────────────────────────────────────┤
│ DOMAIN MODELS                                                │
│  Extended:  mrp.workcenter · mrp.production · mrp.workorder  │
│             mrp.workcenter.productivity(.loss)               │
│             maintenance.equipment · maintenance.request      │
│  New:       fmes.shift · fmes.capacity.matrix                │
│             fmes.production.plan(.line)                      │
│             fmes.production.entry · fmes.manpower.log         │
│             fmes.operator.allocation · fmes.backlog.snapshot │
│             fmes.maintenance.schedule · fmes.alert(.rule)     │
├──────────────────────────────────────────────────────────────┤
│ READ MODELS (SQL views, _auto = False)                       │
│  fmes.production.report · fmes.downtime.report               │
│  fmes.utilization.report · fmes.maintenance.report           │
├──────────────────────────────────────────────────────────────┤
│ AUTOMATION                                                   │
│  ir.cron: nightly backlog snapshot · carry-forward roll      │
│           · preventive maintenance generation                │
│           · alert evaluation · scheduled report email        │
│  base_automation: state-change triggers                      │
├──────────────────────────────────────────────────────────────┤
│ INTEGRATION SEAM  (stubbed — Phase 15 review, built later)   │
│  fmes.integration.adapter (abstract) · fmes.sync.log          │
│  erp_external_id / erp_sync_state mixin on synced models     │
├──────────────────────────────────────────────────────────────┤
│ PERSISTENCE — PostgreSQL 15                                  │
└──────────────────────────────────────────────────────────────┘
```

## 4. Module Dependency Graph

```
                    base
                     │
       ┌─────────────┼──────────────┬─────────────┐
       │             │              │             │
      mail        product         stock          hr
       │             │              │             │
       └──────┬──────┴──────┬───────┘             │
              │             │                     │
             mrp      sale_management             │
              │             │                     │
       maintenance          │                     │
              │             │                     │
       base_automation   portal                   │
              │             │                     │
              └─────────────┴──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │   furnishing_mes    │
                            └─────────────────────┘
```

`__manifest__.py` `depends` list:

```python
'depends': [
    'base', 'mail', 'web',
    'product', 'stock', 'uom',
    'mrp',                 # work centers, work orders, productivity losses, OEE
    'maintenance',         # equipment, requests, MTBF/MTTR
    'hr',                  # employees, departments
    'resource',            # working calendars for shift capacity
    'sale_management',     # mock sales orders (ERP stand-in)
    'portal',              # customer self-service
    'base_automation',     # rule-driven triggers
    'base_import',         # Excel/CSV import
    'spreadsheet_dashboard',
]
```

Every one of these is present in Odoo 18.0 Community — verified against the
`odoo/odoo` 18.0 `addons/` tree.

## 5. Internal Package Structure

```
addons/furnishing_mes/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── mixins.py                  # fmes.erp.sync.mixin
│   ├── fmes_shift.py
│   ├── fmes_capacity_matrix.py
│   ├── mrp_workcenter.py          # extension + equipment bridge
│   ├── mrp_production.py
│   ├── mrp_workorder.py
│   ├── mrp_workcenter_productivity.py
│   ├── maintenance_equipment.py
│   ├── maintenance_request.py
│   ├── fmes_production_plan.py
│   ├── fmes_production_entry.py
│   ├── fmes_manpower.py
│   ├── fmes_backlog.py
│   ├── fmes_maintenance_schedule.py
│   ├── fmes_alert.py
│   ├── fmes_support_ticket.py
│   └── res_users.py               # department scoping
├── services/
│   ├── __init__.py
│   ├── planning_engine.py
│   ├── utilization_service.py
│   ├── backlog_service.py
│   └── alert_engine.py
├── reports/
│   ├── __init__.py
│   ├── production_report.py       # SQL view models
│   ├── downtime_report.py
│   ├── utilization_report.py
│   ├── maintenance_report.py
│   └── templates/                 # QWeb PDF
├── wizards/
│   ├── plan_generator.py
│   ├── production_import.py       # DAY WISE OUTPUT xlsx importer
│   └── report_export.py
├── controllers/
│   ├── __init__.py
│   ├── portal.py                  # customer portal
│   └── shopfloor.py               # terminal JSON endpoints
├── views/                         # one XML file per model + menus.xml
├── data/                          # sequences, loss reasons, crons, templates
├── demo/                          # mock ERP data
├── security/
│   ├── fmes_groups.xml
│   ├── fmes_record_rules.xml
│   └── ir.model.access.csv
├── static/
│   ├── description/               # icon.png, index.html
│   └── src/
│       ├── js/  scss/  xml/       # OWL components
└── tests/
    ├── __init__.py
    └── test_*.py
```

## 6. Key Architectural Decisions (ADRs)

### ADR-001 — Reuse `mrp.workcenter.productivity` for downtime

**Decision.** Downtime is stored in Odoo's native productivity log, extended with
a `fmes_category`, shift link and an approval workflow. We do not create a
separate downtime model.

**Why.** `mrp.workcenter._compute_oee()` already derives OEE from productive
versus blocked time on this model. A parallel model would leave native OEE
permanently wrong. Loss reasons are already a first-class model
(`mrp.workcenter.productivity.loss`) with a `loss_type` classification of
availability / performance / quality / productive — precisely the TEEP taxonomy
the customer's downtime list implies.

**Trade-off.** We inherit Odoo's schema, so custom fields must be additive.
Accepted.

### ADR-002 — Build our own Shop-Floor Terminal

**Decision.** A custom OWL client action, not Odoo's Shop Floor app.

**Why.** `mrp_workorder` (the Shop Floor app) is not in Odoo 18 Community.
Building our own also lets us capture output, downtime reason and manpower in one
tablet flow, which the stock app does not do.

### ADR-003 — Custom scheduling board instead of Gantt

**Decision.** A custom OWL timeline component reading `fmes.production.plan.line`.

**Why.** `web_gantt` is Enterprise-only. Rather than depend on a third-party OCA
backport of uncertain 18.0 maturity, we render a purpose-built board — machines
on the Y axis, time on the X axis, colour-coded by shift and load.

### ADR-004 — SQL views for analytics

**Decision.** Report models are `_auto = False` PostgreSQL views.

**Why.** The customer wants trend analysis over historical records. Python-side
aggregation over `fmes.production.entry` degrades as rows accumulate; a view lets
PostgreSQL aggregate, and Odoo's pivot/graph views read it natively.

### ADR-005 — Manual entry plus Excel import, no IoT

**Decision.** Data enters via the terminal, backoffice forms, or an XLSX importer
modelled on the customer's existing *DAY WISE OUTPUT* sheet.

**Why.** Confirmed with the customer. The importer is also the migration path for
their historical Excel data, which is what makes trend analysis possible from
day one rather than from go-live.

### ADR-006 — Defer ERP 10.8, but not its data contract

**Decision.** No connector is built now, but the sync mixin, `fmes.sync.log`, and
the field-level mapping table are specified in Phase 0 and stubbed in Phase 1.

**Why.** Retrofitting external identity onto records that already exist in
production is a data-migration exercise. Reserving the columns now costs nothing.

## 7. Data Flow — Plan to Report

```
  Mock Sales Orders / Item Master / BOM   (later: ERP 10.8)
                    │
                    ▼
        Manufacturing Orders (mrp.production)
                    │
                    ▼
   ┌────────────────────────────────────────┐
   │  fmes.planning.engine                  │
   │   demand  ×  capacity matrix           │
   │           ×  shift hours               │
   │           ×  machine availability      │
   │           ×  manpower availability     │
   └────────────────────────────────────────┘
                    │
                    ▼
   fmes.production.plan → .plan.line  (machine-wise, shift-wise)
                    │
                    ▼
        fmes.production.entry  (target vs actual)
             ▲              ▲              ▲
             │              │              │
    Shop-Floor        Backoffice      XLSX import
     Terminal            form         (DAY WISE OUTPUT)
             │
             ├──▶ mrp.workcenter.productivity  (downtime + reason)
             └──▶ fmes.manpower.log            (std vs actual manpower)
                    │
                    ▼
   SQL read models → Dashboards · Alerts · PDF/XLSX reports · MIS
                    │
                    └──▶ fmes.backlog.snapshot → carry-forward next day
```

## 8. Non-Functional Requirements

| Attribute | Target | How |
|---|---|---|
| Availability | Single-node, restart-on-failure | `restart: unless-stopped` in Compose |
| Performance | Dashboard under 2 s at 100k production entries | SQL views + indexes on `(date, workcenter_id, shift_id)` |
| Concurrency | 30 internal users + 10 tablets | Odoo default workers; tune `workers`/`limit_*` in `odoo.conf` for prod |
| Data retention | 3 years online | No purge cron; annual archive documented |
| Backup | Nightly full DB + filestore | `pg_dump` + filestore tar, see deployment doc |
| Recovery (RTO/RPO) | RTO 4 h / RPO 24 h | Documented restore runbook |
| Auditability | Who changed what, when | `mail.thread` + `tracking=True` on state and quantity fields |
| Localisation | English, multi-company ready | `company_id` on every operational model |
