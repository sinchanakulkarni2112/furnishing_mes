# Furnishing MES

A Manufacturing Execution System for a furnishing manufacturer, built as a
single custom Odoo 18 Community module (`furnishing_mes`). It turns Odoo's
native Manufacturing and Maintenance apps into capacity-aware production
planning, shop-floor output and downtime capture, machine utilisation and
OEE, preventive/breakdown maintenance, backlog tracking, management
dashboards, an automated reporting suite, and a customer self-service
portal — replacing manual Excel-based planning.

No React, no FastAPI, no Celery/Redis/Nginx: Odoo is both backend and
frontend, `ir.cron` covers scheduling, and Odoo's own server covers HTTP.

---

## Quickstart

```bash
git clone https://github.com/sinchanakulkarni2112/furnishing_mes.git
cd furnishing_mes

cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD to a strong value.

make init
```

Open <http://localhost:8069> and log in with `admin` / `admin`.

Everything runs in Docker — no local Python, PostgreSQL or Odoo install
needed. `make init` installs the module and starts the stack; `make help`
lists every other target (`up`, `down`, `test`, `upgrade`, `psql`, `logs`, …).

---

## Documentation

| | |
|---|---|
| Project overview | [`docs/00-project-overview.md`](docs/00-project-overview.md) |
| Architecture | [`docs/02-architecture.md`](docs/02-architecture.md) |
| Development setup | [`docs/07-development-setup.md`](docs/07-development-setup.md) |
| Deployment & operations | [`docs/08-deployment-operations.md`](docs/08-deployment-operations.md) |
| Administrator guide | [`docs/16-administrator-guide.md`](docs/16-administrator-guide.md) |
| Role manuals (operator, supervisor, plant manager, customer) | [`docs/manuals/`](docs/manuals/) |
| Full documentation index | [`docs/`](docs/) |

---

## Stack

Two containers only — `web` (Odoo 18.0 Community, pinned by digest) and `db`
(PostgreSQL 15). See [`docker-compose.yml`](docker-compose.yml) and
[`docs/07-development-setup.md`](docs/07-development-setup.md) for details.
