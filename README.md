# Furnishing MES

**A Manufacturing Execution System for a furnishing manufacturer, built as a
custom module on Odoo 18 Community Edition, running on Docker.**

Replaces manual Excel-based production planning with capacity-aware automated
planning, digital shop-floor output and downtime capture, machine utilisation and
OEE monitoring, preventive maintenance, backlog management, management dashboards
and a full automated reporting suite.

---

## Current Status

| | |
|---|---|
| **Phase** | 0 of 15 — Documentation complete |
| **Next** | Phase 1 — Docker foundation and module skeleton |
| **Runnable stack** | Lands in Phase 1 |

See [`docs/06-build-plan.md`](docs/06-build-plan.md) for the full phase plan.

---

## Technology

| Layer | Choice |
|---|---|
| Platform | Odoo 18.0 Community Edition |
| Backend | Odoo ORM, Python 3.11+ |
| Frontend | Odoo views (list, form, kanban, pivot, graph, calendar) + OWL 2 components |
| Database | PostgreSQL 15 |
| Security | Odoo `res.groups`, ACLs, record rules, Portal |
| Automation | `ir.cron`, `base_automation`, `mail` |
| Containerisation | Docker + Docker Compose |
| Reports | QWeb (PDF) + xlsxwriter (XLSX) |

Odoo is both the backend and the frontend. There is no separate React app, no
FastAPI service, and no Celery, Redis or Nginx in the standard stack — Odoo's own
cron and web server cover those roles. Rationale in
[`docs/02-architecture.md`](docs/02-architecture.md).

---

## Prerequisites

| Tool | Minimum |
|---|---|
| Docker Engine | 24.0 |
| Docker Compose | v2.20 |
| Git | 2.30 |

Give Docker at least **4 GB RAM** and **2 CPUs**.

On Windows use Docker Desktop with the WSL 2 backend, and clone into the WSL
filesystem rather than `C:\` — bind-mount performance on the Windows filesystem
is poor.

---

## Clone and Run

> These commands work from **Phase 1** onwards, once the Docker stack is committed.

### 1. Clone

```bash
git clone https://github.com/sinchanakulkarni2112/furnishing_mes.git
cd furnishing_mes
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` and set real values:

```ini
POSTGRES_DB=postgres
POSTGRES_USER=odoo
POSTGRES_PASSWORD=<choose a strong password>
ADMIN_PASSWD=<choose a strong master password>
ODOO_PORT=8069
```

`.env` is git-ignored and must never be committed.

### 3. Start

```bash
docker compose up -d
docker compose logs -f web
```

Wait for `odoo.modules.loading: Modules loaded.`, then open
<http://localhost:8069>.

### 4. Create the database

On first launch Odoo shows its database creation screen:

| Field | Value |
|---|---|
| Master Password | the `ADMIN_PASSWD` from your `.env` |
| Database Name | `furnishing_mes` |
| Email | your admin login |
| Password | your admin password |
| Demo data | **tick it** — the mock ERP dataset depends on it |

To skip the wizard entirely:

```bash
docker compose run --rm web odoo \
  -d furnishing_mes -i furnishing_mes \
  --without-demo=False --stop-after-init
docker compose up -d
```

### 5. Install the module

If you used the wizard: **Apps → Update Apps List → search "Furnishing MES" → Install**.

That's it — the plant demo data (departments, machines, shifts, capacity matrix,
mock orders) loads with the module, so the system is immediately explorable.

---

## Common Commands

| Command | Does |
|---|---|
| `make up` | Start the stack |
| `make down` | Stop it |
| `make logs` | Tail Odoo logs |
| `make restart` | Restart Odoo only |
| `make upgrade` | Apply module changes |
| `make test` | Run the test suite |
| `make shell` | Odoo interactive shell |
| `make psql` | PostgreSQL prompt |
| `make clean` | **Destroy** containers and volumes (all data lost) |

Without `make`, each maps to a `docker compose` command — see
[`docs/07-development-setup.md`](docs/07-development-setup.md) §4.

After changing XML, security CSV or Python: `make upgrade`.
After changing JS or SCSS: reload the browser.

---

## Project Structure

```
furnishing_mes/
├── addons/furnishing_mes/      # the Odoo module
│   ├── models/                 # domain models
│   ├── services/               # planning engine, alert engine, ...
│   ├── reports/                # SQL read models + QWeb templates
│   ├── wizards/                # plan generator, importers
│   ├── controllers/            # portal + terminal endpoints
│   ├── views/                  # XML views and menus
│   ├── security/               # groups, ACLs, record rules
│   ├── data/                   # sequences, crons, seed config
│   ├── demo/                   # mock ERP dataset
│   ├── static/src/             # OWL components, SCSS
│   └── tests/
├── config/odoo.conf
├── docs/                       # design and delivery documentation
├── scripts/                    # backup, restore, load seeding
├── docker-compose.yml
├── docker-compose.prod.yml
└── Makefile
```

---

## Features by Requirement

| # | Requirement | Phase |
|---|---|---|
| 1 | Production planning automation | 3 |
| 2 | Daily production plan and output tracking | 4 |
| 3 | Production monitoring | 4, 6 |
| 4 | Backlog and carry-forward management | 9 |
| 5 | Machine utilisation monitoring | 6 |
| 6 | Downtime management | 5 |
| 7 | Machine maintenance management | 7 |
| 8 | Production resource management | 8 |
| 9 | Analytics and dashboards | 10 |
| 10 | Alerts and notifications | 11 |
| 11 | ERP 10.8 integration | **Deferred** — [roadmap](docs/09-erp-integration-roadmap.md) |
| 12 | Reporting requirements | 12 |

Detailed mapping: [`docs/01-requirements-traceability.md`](docs/01-requirements-traceability.md).

---

## User Roles

| Role | Type | Access |
|---|---|---|
| **Operator** | Internal | Shop-Floor Terminal only — assigned work orders, output entry, downtime logging |
| **Supervisor** | Internal | Shift scheduling, approvals, maintenance escalation, operator allocation, department reports |
| **Plant Manager** | Internal | Full control — planning, maintenance, inventory, costing, MIS dashboards, configuration |
| **Customer** | Portal | `/my/home` — own orders, progress, support tickets |

Enforced by ACLs and record rules, not merely hidden menus. See
[`docs/04-security-model.md`](docs/04-security-model.md).

---

## Documentation

| Doc | Contents |
|---|---|
| [Documentation index](docs/README.md) | Where to find everything |
| [00 — Project Overview](docs/00-project-overview.md) | Problem, scope, success criteria |
| [01 — Requirements Traceability](docs/01-requirements-traceability.md) | Requirement → feature → phase |
| [02 — Architecture](docs/02-architecture.md) | System design and ADRs |
| [03 — Data Model](docs/03-data-model.md) | Models, fields, ERD |
| [04 — Security Model](docs/04-security-model.md) | Groups, ACLs, record rules, hardening |
| [05 — UI / UX Design](docs/05-ui-ux-design.md) | Views, menus, OWL screens |
| [06 — Build Plan](docs/06-build-plan.md) | **Phase-by-phase delivery plan** |
| [07 — Development Setup](docs/07-development-setup.md) | Local development |
| [08 — Deployment & Operations](docs/08-deployment-operations.md) | On-prem deployment, backup, upgrade |
| [09 — ERP Integration Roadmap](docs/09-erp-integration-roadmap.md) | Deferred ERP 10.8 design |
| [10 — Testing & QA](docs/10-testing-qa.md) | Test strategy |
| [11 — Reporting & Analytics](docs/11-reporting-analytics.md) | Metric definitions and report specs |
| [12 — Git Workflow](docs/12-git-workflow.md) | Commits and per-phase pushes |
| [13 — Edition Constraints](docs/13-odoo-edition-constraints.md) | Community vs Enterprise |
| [14 — Glossary](docs/14-glossary.md) | Terminology |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `port 8069 already allocated` | Change `ODOO_PORT` in `.env` |
| Module not in the Apps list | Developer mode → Apps → *Update Apps List* |
| XML changes not appearing | `make upgrade` |
| JS/SCSS changes not appearing | Hard-refresh the browser |
| `db` container restarting | `make clean` (stale volume from another Postgres major) |
| Very slow on Windows | Clone into the WSL 2 filesystem, not `C:\` |

More: [`docs/07-development-setup.md`](docs/07-development-setup.md) §10.

---

## License

LGPL-3, consistent with Odoo Community.
