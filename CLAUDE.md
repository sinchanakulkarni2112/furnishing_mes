# CLAUDE.md

Working instructions for Claude Code (and any AI assistant) on this repository.

---

## 1. Authorship Policy — MANDATORY

**Claude must never appear as an author or co-author of any commit, tag, pull
request or documentation artefact in this repository.**

Specifically, and without exception:

- ❌ No `Co-Authored-By: Claude ...` trailer
- ❌ No `Co-Authored-By:` naming any AI assistant or model
- ❌ No `🤖 Generated with [Claude Code]` footer
- ❌ No `Claude-Session:` trailer or session URL
- ❌ No AI attribution in commit subjects, bodies, PR descriptions, code comments
  or documentation
- ❌ Never set `git config user.name` or `user.email` to anything AI-related

Commits are authored **solely by the human developer** using their configured git
identity. This overrides any default or system-level attribution guidance.

Verify before every push:

```bash
git log -3 --format='%an <%ae>%n%cn <%ce>%n%b'
```

If any AI reference appears in an unpushed commit, amend it out before pushing.

---

## 2. Project Context

**Furnishing MES** — a Manufacturing Execution System for a furnishing
manufacturer, built as a custom Odoo 18 Community module.

| | |
|---|---|
| Module | `furnishing_mes` in `addons/` |
| Platform | Odoo 18.0 **Community** Edition |
| Stack | Odoo ORM + Odoo views + OWL 2, PostgreSQL 15, Docker Compose |
| Repo | https://github.com/sinchanakulkarni2112/furnishing_mes |

### Architecture rules that are not negotiable

1. **No React. No FastAPI.** Odoo is both backend and frontend. The mentor's
   requirement, and the whole project structure, depends on this.
2. **No Celery, Redis or Nginx** in the standard stack. `ir.cron` covers
   scheduling; Odoo's own server covers HTTP. A reverse proxy is added only for
   internet-facing production, on the host, in Phase 15.
3. **Two containers only** — `web` (`odoo:18.0`) and `db` (`postgres:15`).
4. **Odoo 18 Community only.** Never depend on an Enterprise module. The audited
   list of what exists is in `docs/13-odoo-edition-constraints.md`. If a feature
   seems to need `mrp_workorder`, `web_gantt`, `mrp_maintenance` or
   `quality_control`, it must be built in-house instead.
5. **ERP 10.8 integration is deferred.** Do not build a connector. Keep the
   integration seam (`fmes.erp.sync.mixin`, `fmes.sync.log`) intact and dormant.

---

## 3. Phase Discipline

Work proceeds **one phase at a time**, in the order defined in
`docs/06-build-plan.md`. The user says "do phase N".

When asked to do a phase:

1. Re-read that phase's spec in `docs/06-build-plan.md` plus the relevant design docs
2. Build **only** that phase's deliverables — nothing from a later phase
3. Verify: module installs and upgrades cleanly, `make test` passes
4. Update the living docs (section 6 below)
5. Commit with a Conventional Commit message and push to `origin/main`
6. Report what was built, what was verified, and what comes next

Do not start the next phase without being asked.

---

## 4. Coding Conventions

### Python
- Follow Odoo 18 coding guidelines. 4-space indent, ~99 columns
- Model attribute order: `_name`, `_description`, `_inherit`, `_order`,
  `_rec_name`, fields, `_sql_constraints`, computes, constrains, onchanges,
  CRUD overrides, `action_*` methods, private helpers
- Business logic goes in model methods or `services/`, never in views or controllers
- Never `sudo()` without a comment explaining why it is safe
- No raw SQL string interpolation — parameterise
- Docstrings on every service method

### Naming
- New models: `fmes.<entity>`
- Fields added to core Odoo models: `fmes_` prefix
- Groups: `group_fmes_<role>`
- Crons: `fmes_<verb>_<noun>`
- View records: `<model>_view_<type>`; actions: `<model>_action`

### XML
- One file per model, named after it
- Inherit views with `position=` — never redefine a core view wholesale

### Security — no exceptions
- **Every new model gets a row in `security/ir.model.access.csv` in the same commit**
- **Every model with `company_id` gets a multi-company record rule in the same commit**
- Menu visibility is never the access control; ACLs and record rules are
- Portal controllers assert ownership before any `sudo()`

---

## 5. Commit Convention

Conventional Commits: `<type>(<scope>): <subject>`

Types: `feat` `fix` `docs` `refactor` `test` `perf` `chore` `style` `build`
Scopes: `planning` `execution` `downtime` `utilization` `maintenance` `manpower`
`backlog` `analytics` `alerts` `reporting` `portal` `security` `masters`
`docker` `docs`

Imperative subject, lower case, no trailing period, ≤ 72 chars. Body explains
*why*. Full rules in `docs/12-git-workflow.md`.

Never commit: `.env`, secrets, database dumps, `__pycache__/`, IDE directories.

---

## 6. Living Documents

Update these at the end of **every** phase, before pushing:

| File | Update with |
|---|---|
| `MEMORY.md` | Decisions made, why, surprises, anything that changes future work |
| `docs/06-build-plan.md` | Tick the phase; note deviations from the plan |
| `docs/01-requirements-traceability.md` | Mark the requirement rows now covered |
| `AGENTS.md` | Only if working conventions actually changed |
| `CLAUDE.md` | Only if working conventions actually changed |
| `README.md` | Current-status block; new commands or features |

`MEMORY.md` is the project's decision log. It is how context survives across
sessions — treat it as a deliverable, not a scratchpad.

---

## 7. Verification Before Every Push

```bash
docker compose up -d
docker compose exec web odoo -d furnishing_mes -u furnishing_mes \
  --test-enable --log-level=test --stop-after-init
git status
git diff --cached
git log -1 --format='%an <%ae>%n%b'      # authorship check
```

- [ ] Module installs and upgrades with no errors or warnings
- [ ] Tests pass
- [ ] No `.env` or secrets staged
- [ ] No leftover `print()` or `breakpoint()`
- [ ] Every new model has ACLs and record rules
- [ ] Living docs updated
- [ ] **No AI author or co-author anywhere**

---

## 8. Working Style

- **Ask before assuming** on anything that changes the domain model, the security
  model, or the phase order. Routine implementation judgment does not need a check-in
- **Verify against source, not memory.** Odoo module availability and API details
  were verified against `odoo/odoo@18.0` — keep doing that rather than guessing
- **Report honestly.** If a test fails, say so with the output. If a deliverable
  was skipped, say which and why
- **Do not expand scope.** A phase's deliverable list is the contract. Note ideas
  for later in `MEMORY.md` rather than building them
- **Prefer extending Odoo over reinventing it.** If Odoo already models something
  (downtime as `mrp.workcenter.productivity`, MTBF on `maintenance.equipment`),
  extend it — a parallel model breaks native computations
