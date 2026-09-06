# 07 — Development Setup

Everything runs in Docker. You do not need Python, PostgreSQL or Odoo installed
on your machine.

---

## 1. Prerequisites

| Tool | Minimum | Check |
|---|---|---|
| Docker Engine | 24.0 | `docker --version` |
| Docker Compose | v2.20 | `docker compose version` |
| Git | 2.30 | `git --version` |

On Windows, Docker Desktop with the WSL 2 backend. On macOS, Docker Desktop. On
Linux, Docker Engine plus the Compose plugin.

Allocate at least **4 GB RAM** and **2 CPUs** to Docker.

---

## 2. First Run

```bash
git clone https://github.com/sinchanakulkarni2112/furnishing_mes.git
cd furnishing_mes

cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD to a strong value.

make init
```

Open <http://localhost:8069> and log in with `admin` / `admin`.

`make init` wraps two commands, if you would rather run them directly:

```bash
docker compose run --rm web odoo -d furnishing_mes -i furnishing_mes --stop-after-init
docker compose up -d
```

The first run takes a few minutes while Docker pulls the images and Odoo
installs the dependency modules.

### Using the database wizard instead

Run `docker compose up -d` on its own and open <http://localhost:8069>. Odoo
shows its database creation screen:

| Field | Value |
|---|---|
| Master Password | `fmes_dev_master_change_in_production` (from `config/odoo.conf`) |
| Database Name | `furnishing_mes` |
| Email / Password | your admin login |
| Demo data | **check it** — the mock ERP dataset depends on it |

Then **Apps -> Update Apps List -> search "Furnishing MES" -> Install**.

The master password lives in `config/odoo.conf` because Odoo 18 has **no
`--admin-passwd` command-line option** - it is a config-file setting only. The
committed value is an explicit development placeholder, and the stack binds to
`127.0.0.1` by default, so the database manager is not reachable from the
network. Production generates a strong value into a git-ignored config
(Phase 15).

### Reaching it from a tablet

Set `ODOO_BIND=0.0.0.0` in `.env`, then `make down && make up`, and browse to
`http://<your-machine-ip>:8069`. Trusted networks only - the development
configuration is not hardened for exposure.

---

## 3. Project Layout

```
furnishing_mes/
├── addons/
│   └── furnishing_mes/          # the module (bind-mounted into the container)
├── config/
│   └── odoo.conf
├── docs/
├── scripts/
├── docker-compose.yml
├── docker-compose.prod.yml      # Phase 15
├── .env.example
├── .env                         # git-ignored
├── Makefile
├── README.md
├── CLAUDE.md
├── AGENTS.md
└── MEMORY.md
```

`./addons` is bind-mounted, so edits on the host are visible in the container
immediately. Python changes still need a module upgrade or a server restart.

---

## 4. Daily Workflow

The `Makefile` wraps the common commands. On Windows use Git Bash, WSL, or run
the underlying `docker compose` command shown in each row.

| Command | Does | Underlying |
|---|---|---|
| `make up` | Start the stack | `docker compose up -d` |
| `make down` | Stop it | `docker compose down` |
| `make logs` | Tail Odoo logs | `docker compose logs -f web` |
| `make restart` | Restart Odoo only | `docker compose restart web` |
| `make init` | Create the database and install | `docker compose run --rm web odoo -d $(DB) -i furnishing_mes --stop-after-init` |
| `make upgrade` | Upgrade the module | `docker compose run --rm web odoo -d $(DB) -u furnishing_mes --stop-after-init` then restart |
| `make install` | Install into an existing database | `... -i furnishing_mes --stop-after-init` |
| `make test` | Run the module's tests | `... -u furnishing_mes --test-enable --test-tags /furnishing_mes --log-level=test --stop-after-init` |
| `make shell` | Odoo interactive shell | `docker compose run --rm web odoo shell -d $(DB)` |
| `make psql` | PostgreSQL prompt | `docker compose exec db psql -U odoo -d $(DB)` |
| `make bash` | Shell inside the web container | `docker compose exec web bash` |
| `make clean` | **Destroy** containers and volumes | `docker compose down -v` |

### What needs which action

| You changed | Do this |
|---|---|
| XML views, data, security CSV | `make upgrade` |
| Python models or services | `make upgrade` (schema may change) |
| Python without schema change | `make restart` is usually enough |
| JS / SCSS / OWL templates | Reload the browser; hard-refresh if assets are cached |
| `__manifest__.py` | `make upgrade` |
| `docker-compose.yml` or `odoo.conf` | `make down && make up` |

If assets look stale, enable **Developer Mode → Become Superuser** and use
*Settings → Technical → Regenerate Assets Bundles*.

---

## 5. Developer Mode

Settings → General Settings → Developer Tools → **Activate the developer mode**,
or append `?debug=1` to the URL. Use `?debug=assets` when debugging OWL or SCSS
so bundles are served unminified.

Developer mode gives you the Technical menu: models, fields, views, ACLs, record
rules, scheduled actions, and the ability to inspect any field's definition from
the UI. It is the fastest way to check that an ACL or record rule actually took
effect.

---

## 6. Debugging

### Logs

```bash
docker compose logs -f web
docker compose logs -f web | grep -i error
```

Raise verbosity temporarily in `config/odoo.conf`:

```ini
log_level = debug
log_handler = odoo.addons.furnishing_mes:DEBUG
```

The `log_handler` form keeps the noise down: debug output for our module only.

### Interactive debugging

Set `workers = 0` in `odoo.conf` (already the default for development) so the
process is single-threaded, then use `breakpoint()` in your code and attach:

```bash
docker compose exec web python3 -c "print('attached')"   # sanity check
docker attach $(docker compose ps -q web)                # for pdb interaction
```

Detach with `Ctrl-P Ctrl-Q` — **not** `Ctrl-C`, which stops the container.

### The Odoo shell

The fastest way to test a service method:

```bash
make shell
```
```python
env['fmes.planning.engine'].generate(
    date_from='2026-09-07', date_to='2026-09-13')
env.cr.rollback()      # nothing is committed unless you say so
```

### SQL

```bash
make psql
```
```sql
\dt fmes_*
EXPLAIN ANALYZE SELECT * FROM fmes_production_report WHERE date > '2026-01-01';
```

---

## 7. Coding Standards

Follow the [Odoo development guidelines](https://www.odoo.com/documentation/18.0/contributing/development/coding_guidelines.html).

**Python**
- 4-space indent, ~99 column limit
- Model attribute order: `_name`, `_description`, `_inherit`, `_order`,
  `_rec_name`, then fields, then `_sql_constraints`, `compute`, `constrains`,
  `onchange`, CRUD overrides, actions, then private helpers
- Private methods prefixed `_`; action methods named `action_*`
- Never `sudo()` without a comment explaining why it is safe
- No raw SQL string interpolation — parameterise, always
- Docstrings on every service method: what it does, what it returns, what it raises

**XML**
- One file per model, named after it (`fmes_production_entry_views.xml`)
- Record ids follow `<model>_view_<type>` and `<model>_action`
- Always `<field name="x" position="after">` style inheritance; never redefine a
  core view wholesale

**Naming**
- New models: `fmes.<entity>`
- Fields added to core models: `fmes_` prefix, so provenance is obvious
- Groups: `group_fmes_<role>`
- Crons: `fmes_<verb>_<noun>`

**Security**
- No model is committed without a row in `ir.model.access.csv`
- Any model with `company_id` gets a multi-company record rule in the same commit

---

## 8. Testing

```bash
make test                                   # whole module
docker compose exec web odoo -d furnishing_mes \
  -u furnishing_mes --test-enable \
  --test-tags /furnishing_mes:TestPlanningEngine --stop-after-init
```

Tests live in `addons/furnishing_mes/tests/`, inherit
`odoo.tests.common.TransactionCase` (or `HttpCase` for controllers and OWL), and
are tagged. See [`10-testing-qa.md`](10-testing-qa.md).

---

## 8b. Running a Second Instance

Containers, volumes and the network are all prefixed with the Compose project
name (`furnishing-mes`). To run a second clone on the same machine — a review
copy alongside your working copy, say — give it its own project name and ports:

```bash
export COMPOSE_PROJECT_NAME=fmes-review     # PowerShell: $env:COMPOSE_PROJECT_NAME="fmes-review"
# and set ODOO_PORT / ODOO_LONGPOLL_PORT to free values in that clone's .env
docker compose up -d
```

Volume names are deliberately **not** pinned in `docker-compose.yml`. If they
were, a second clone would attach to the first one's PostgreSQL data directory
with a different `POSTGRES_PASSWORD` and fail with
`password authentication failed for user "odoo"`.

---

## 9. Resetting

```bash
make clean          # removes containers AND volumes — all data is lost
make up
```

To drop only the database but keep the images:

```bash
docker compose exec db dropdb -U odoo furnishing_mes
docker compose run --rm web odoo -d furnishing_mes -i furnishing_mes --stop-after-init
```

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `port 8069 already allocated` | Something else on the port | Change the host port in `docker-compose.yml`, e.g. `8070:8069` |
| Module not in the Apps list | Apps list is stale | Developer mode → Apps → *Update Apps List* |
| `database ... does not exist` | Not yet initialised | Run the init command in section 2 |
| Changes to XML not showing | Module not upgraded | `make upgrade` |
| JS/SCSS changes not showing | Asset bundle cached | Hard refresh, or regenerate assets bundles |
| `permission denied` on `./addons` | Host file ownership (Linux) | `sudo chown -R $USER:$USER addons` |
| `db` container restarting | Stale volume from a different Postgres major | `make clean` and start again |
| Odoo starts then exits | Config error | `docker compose logs web` — the traceback names the line |
| Very slow on Windows | Files on the Windows filesystem | Clone into the WSL 2 filesystem (`\\wsl$\...`), not `C:\` |
| `Address already in use: 8069` when running odoo | Used `docker compose exec`, which shares the running server's port | Use `docker compose run --rm web odoo ...` — this is what the Makefile does |
| `connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed` | `exec` bypasses the image entrypoint, so the `--db_*` arguments are never built | Use `run --rm`. The `PG*` variables in `docker-compose.yml` also cover the `exec` case |
| `docker-credential-desktop: executable file not found` | Docker Desktop's bin directory is not on Git Bash's PATH | Run docker commands from PowerShell, or add `C:\Program Files\Docker\Docker\resources\bin` to PATH |
esources\bin` to PATH |
| `Cannot connect to the Docker daemon` | Docker Desktop is not running | Start Docker Desktop and wait for the whale icon to settle |
