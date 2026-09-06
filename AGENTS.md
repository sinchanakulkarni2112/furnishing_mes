# AGENTS.md

Operating guide for any AI coding agent working in this repository.
`CLAUDE.md` holds the same rules; this file is the tool-agnostic entry point.

---

## Hard Rules

1. **Commit identity is `sinchanakulkarni2112`.** Set repo-locally:
   `git config user.name "sinchanakulkarni2112"` and
   `git config user.email "323928844+sinchanakulkarni2112@users.noreply.github.com"`.
   No commit may be authored by `shreyassridhar44` / `shreyassridhar146@gmail.com`.
   The remote must be `git@github-sinchan:sinchanakulkarni2112/furnishing_mes.git`
   — HTTPS authenticates as the wrong account and 403s. See `CLAUDE.md` §1a.
2. **No AI authorship.** No agent may appear as author or co-author of any
   commit, tag, PR or document. No `Co-Authored-By` trailer naming an assistant,
   no "generated with" footer, no session URL, no AI attribution anywhere in
   commit metadata, code comments or docs. See `CLAUDE.md` §1b.
3. **No React, no FastAPI.** Odoo 18 is both backend and frontend. This is the
   mentor's stated requirement and the basis of the whole design.
4. **Community edition only.** Never depend on an Odoo Enterprise module.
   Verified availability list: `docs/13-odoo-edition-constraints.md`.
5. **Two containers only** — `web` (`odoo:18.0`) and `db` (`postgres:15`).
   No Celery, Redis or Nginx in the standard stack.
6. **ERP 10.8 integration stays deferred.** Keep the seam dormant; do not build a
   connector.
7. **One phase at a time.** Build exactly the phase asked for, per
   `docs/06-build-plan.md`. Never work ahead.
8. **No model without ACLs.** A new model and its `ir.model.access.csv` rows and
   record rules ship in the same commit.
9. **Never block on the customer.** Adopt the industry-standard default, record
   it with an assumption ID in `docs/15-open-questions-and-assumptions.md`, and
   implement it as configuration so the real answer is a data edit later. Put new
   questions for the manager/customer in Part A of that document.

---

## Repository Map

```
addons/furnishing_mes/   the Odoo module — all application code
config/odoo.conf         Odoo server configuration
docs/                    design and delivery documentation (start at docs/README.md)
scripts/                 backup, restore, load-seeding
docker-compose.yml       the development stack
Makefile                 command shortcuts
README.md                clone-and-run instructions
CLAUDE.md                agent working rules (authoritative)
AGENTS.md                this file
MEMORY.md                decision log — updated every phase
customer_requirements.txt  the original customer brief
```

---

## Before You Start Any Task

1. Read `MEMORY.md` — it carries decisions from previous phases
2. Read the phase spec in `docs/06-build-plan.md`
3. Read the design docs the phase depends on:
   - Models → `docs/03-data-model.md`
   - Permissions → `docs/04-security-model.md`
   - Screens → `docs/05-ui-ux-design.md`
   - Metrics and reports → `docs/11-reporting-analytics.md`
   - Why something is the way it is → `docs/02-architecture.md` (ADRs)
4. Confirm nothing you plan to use is Enterprise-only

---

## Task Loop for a Phase

```
read spec → implement deliverables → make upgrade → make test
    → update MEMORY.md + build plan + traceability
    → review diff → commit → push → report
```

**Report back** with: what was built, what was verified (with evidence), anything
deferred and why, and what the next phase covers.

---

## Verification Commands

```bash
docker compose up -d
docker compose logs -f web

# apply changes
docker compose exec web odoo -d furnishing_mes -u furnishing_mes --stop-after-init
docker compose restart web

# run tests
docker compose exec web odoo -d furnishing_mes -u furnishing_mes \
  --test-enable --log-level=test --stop-after-init

# inspect
docker compose exec web odoo shell -d furnishing_mes
docker compose exec db psql -U odoo -d furnishing_mes
```

Or `make up` / `make upgrade` / `make test` / `make shell` / `make psql`.

---

## Conventions Cheat Sheet

| Thing | Convention |
|---|---|
| New model | `fmes.<entity>` |
| Field on a core model | `fmes_` prefix |
| Security group | `group_fmes_<role>` |
| Cron | `fmes_<verb>_<noun>` |
| View record | `<model>_view_<type>` |
| Action record | `<model>_action` |
| Service | `AbstractModel` in `services/`, name `fmes.<thing>.engine` or `.service` |
| Report model | `_auto = False` SQL view in `reports/` |
| Commit | `<type>(<scope>): <imperative subject>` |
| Module version | `18.0.<phase>.<minor>.<patch>` |

---

## Do Not

- Do not add a dependency without checking it exists in Odoo 18 Community
- Do not create a parallel model for something Odoo already models — extend it
- Do not put business logic in views or controllers
- Do not use `sudo()` without a justifying comment
- Do not interpolate strings into SQL
- Do not hide data with menu visibility and call it security
- Do not commit `.env`, dumps, or generated artefacts
- Do not load mock/demo records from `data/` — they belong in `demo/`
- Do not build anything from a future phase, however small

---

## When Blocked

**A missing customer answer is never a blocker.** Adopt the standard default,
give it an assumption ID in `docs/15-open-questions-and-assumptions.md`, make it a
configuration record, and add the question to Part A. Carry on.

If a phase spec is ambiguous in a way that changes the domain model, the security
model, or the phase order — **ask the user**, do not guess. For ordinary
implementation judgment, decide, proceed, and record the decision in `MEMORY.md`.

If something in the design docs turns out to be wrong (an Odoo API differs, a
model does not exist), fix the doc in the same commit as the code. The docs are
the specification; leaving them wrong is a defect.
