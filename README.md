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
| **Phase** | 12 of 15 — Reporting suite ✅ |
| **Next** | Phase 13 — Customer portal |
| **Module version** | `18.0.12.0.0` |
| **Verified** | Installs clean on Odoo 18.0 Community (with and without demo data) · 400 tests passing · no install warnings · all ten reports (PDF + XLSX) and scheduled email delivery verified against fixture data, with a real generated PDF confirmed by hand |

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

### 1. Clone

```bash
git clone https://github.com/sinchanakulkarni2112/furnishing_mes.git
cd furnishing_mes
```

### 2. Configure

```bash
cp .env.example .env
```

Open `.env` and set **`POSTGRES_PASSWORD`** to a strong value. The stack
deliberately refuses to start if it is unset, so it can never boot on a
well-known default.

`.env` is git-ignored and must never be committed.

### 3. Create the database and install the module

```bash
docker compose run --rm web odoo -d furnishing_mes -i furnishing_mes --stop-after-init
docker compose up -d
```

The first command creates the `furnishing_mes` database and installs the module
with all its dependencies and demo data. The second starts the stack.

Takes a few minutes the first time, while Docker pulls the images and Odoo
installs the dependency modules.

> On Windows, run docker commands from **PowerShell**. In Git Bash they can fail
> with `docker-credential-desktop: executable file not found`, because Docker
> Desktop's `resources\bin` directory is not on Git Bash's PATH.

> If you have `make` (Linux, macOS, or WSL), `make init` does both steps.
> `make` is optional — every target is just a `docker compose` command, listed
> in [Common Commands](#common-commands) below.

### 4. Open it

<http://localhost:8069> — log in with `admin` / `admin`.

The **Furnishing MES** app appears in the app menu. The admin user is a Plant
Manager, so everything is visible.

> **Prefer the graphical setup?** Skip step 3, run `docker compose up -d`, and
> use Odoo's database wizard at <http://localhost:8069>. The development master
> password is `fmes_dev_master_change_in_production`, set in `config/odoo.conf`.
> Tick **Load demonstration data**, then install the module from
> **Apps → Update Apps List → "Furnishing MES"**.

### Reaching it from a tablet or another device

The stack binds to `127.0.0.1` by default. To reach it from a shop-floor tablet
on the same network, set `ODOO_BIND=0.0.0.0` in `.env`, restart with
`docker compose down && docker compose up -d`, and browse to
`http://<your-machine-ip>:8069`. Only do this on a trusted network — the
development configuration is not hardened for exposure.
---

## Common Commands

`make` is a convenience wrapper. If you do not have it, use the command in the
right-hand column directly — that is all the target runs.

| `make` target | Does | Underlying command |
|---|---|---|
| `make help` | List every target | — |
| `make init` | Create the database and install the module | `docker compose run --rm web odoo -d furnishing_mes -i furnishing_mes --stop-after-init` |
| `make up` | Start the stack | `docker compose up -d` |
| `make down` | Stop it (data preserved) | `docker compose down` |
| `make logs` | Tail Odoo logs | `docker compose logs -f web` |
| `make restart` | Restart Odoo only | `docker compose restart web` |
| `make upgrade` | Apply module changes | `docker compose run --rm web odoo -d furnishing_mes -u furnishing_mes --stop-after-init` |
| `make test` | Run the test suite | `docker compose run --rm web odoo -d furnishing_mes -u furnishing_mes --test-enable --test-tags /furnishing_mes --log-level=test --stop-after-init` |
| `make shell` | Odoo interactive shell | `docker compose run --rm web odoo shell -d furnishing_mes` |
| `make psql` | PostgreSQL prompt | `docker compose exec db psql -U odoo -d furnishing_mes` |
| `make ps` | Container status | `docker compose ps` |
| `make clean` | **Destroy** containers and volumes | `docker compose down -v` |

**Always use `docker compose run`, never `exec`, to run Odoo commands.** `exec`
bypasses the image entrypoint (so the database arguments are never built) and
collides with the running server on port 8069.

More detail: [`docs/07-development-setup.md`](docs/07-development-setup.md) §4.

After changing XML, security CSV or Python, apply it with the `upgrade`
command above, then `docker compose restart web`.

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
├── scripts/                    # backup, restore, load seeding (Phase 14-15)
├── docker-compose.yml
├── docker-compose.prod.yml      # Phase 15
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
| [15 — Open Questions & Assumptions](docs/15-open-questions-and-assumptions.md) | Questions for the customer, and the defaults we build on |

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
