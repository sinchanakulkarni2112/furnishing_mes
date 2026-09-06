# 12 — Git Workflow & Contribution Guide

Repository: <https://github.com/sinchanakulkarni2112/furnishing_mes>

---

## 1. Branching

The project runs **trunk-based on `main`**. Each phase is a coherent increment,
reviewed as a whole, and pushed to `main` on completion.

| Branch | Purpose |
|---|---|
| `main` | The delivered work. Always installable, always green |
| `phase/N-slug` | Optional working branch for a phase, merged to `main` at the end |
| `fix/<slug>` | Defect found after a phase closed |

`main` must never be left in a state where `docker compose up -d` plus module
install fails. If a phase cannot be completed, its partial work stays on a branch.

---

## 2. Commit Convention

[Conventional Commits](https://www.conventionalcommits.org/).

```
<type>(<scope>): <subject>

<body — what and why, not how>
```

| Type | Use for |
|---|---|
| `feat` | New functionality |
| `fix` | Defect correction |
| `docs` | Documentation only |
| `refactor` | Restructuring with no behaviour change |
| `test` | Tests only |
| `perf` | Performance work |
| `chore` | Tooling, dependencies, housekeeping |
| `style` | Formatting only |
| `build` | Docker, compose, manifest packaging |

Scopes used in this project: `planning`, `execution`, `downtime`, `utilization`,
`maintenance`, `manpower`, `backlog`, `analytics`, `alerts`, `reporting`,
`portal`, `security`, `masters`, `docker`, `docs`.

**Rules**
- Subject in the imperative, lower case, no trailing full stop, ≤ 72 characters
- Body explains *why*, wrapped at 72 columns
- One logical change per commit; a phase may be several commits
- Never commit `.env`, database dumps, `__pycache__/`, or IDE directories

**Examples**

```
feat(planning): add capacity-aware production planning engine

Generates machine-wise, shift-wise plans from the capacity matrix,
deriving available hours from shift net time, machine availability
and allocated manpower. Replaces manual Excel planning (R1).

docs: add complete project documentation and phase-wise build plan

fix(downtime): prevent duplicate maintenance requests on escalation

test: add security record-rule suite for operator scoping
```

---

## 3. Authorship Policy

**Commits are authored solely by the human developer.**

- No AI tool is named as author or co-author
- No `Co-Authored-By:` trailer naming an assistant
- No generated-with footer or promotional trailer
- No AI attribution in commit bodies, PR descriptions, or documentation

This is a hard project rule, recorded in `CLAUDE.md` and `AGENTS.md`. Verify
before pushing:

```bash
git log -3 --format='%an <%ae>%n%b'
```

Nothing in the author, committer or body fields should reference an assistant.

---

## 4. Per-Phase Push Protocol

At the end of every phase, in this order:

1. **Verify** — module installs and upgrades cleanly; `make test` passes
2. **Update the living docs**
   - `docs/06-build-plan.md` — tick the phase, note anything that changed
   - `MEMORY.md` — decisions taken, why, and anything that surprised us
   - `AGENTS.md` / `CLAUDE.md` — only if conventions actually changed
   - `docs/01-requirements-traceability.md` — mark the covered requirement rows
3. **Review the diff** — `git status`, `git diff`; confirm no secrets, no
   `.env`, no stray debug prints or `breakpoint()` calls
4. **Stage and commit** with a Conventional Commit message
5. **Push** — `git push origin main`
6. **Confirm** — `git log --oneline -1` and verify the authorship policy held

```bash
git status
git add -A
git commit -m "feat(planning): add capacity-aware production planning engine" \
           -m "Generates machine-wise, shift-wise plans from the capacity matrix. Covers R1."
git push origin main
git log -1 --format='%an <%ae>'
```

---

## 5. What Is Committed

**Committed**

```
addons/furnishing_mes/**        docs/**              scripts/**
config/odoo.conf                docker-compose*.yml  Makefile
.env.example                    .gitignore           README.md
CLAUDE.md                       AGENTS.md            MEMORY.md
customer_requirements.txt
```

**Never committed** — enforced by `.gitignore`

```
.env                    *.pyc, __pycache__/     *.dump, *.sql
filestore/              .idea/, .vscode/        .DS_Store
node_modules/           *.log                   backups/
```

`config/odoo.conf` is committed because it holds no secrets — the admin password
and database credentials come from the environment. If that ever stops being
true, the file moves to `.gitignore` and a `.example` takes its place.

---

## 6. Pre-Push Checklist

- [ ] `docker compose up -d` works from a clean clone
- [ ] Module installs and upgrades with no errors or warnings
- [ ] `make test` passes
- [ ] No `.env`, secrets, credentials or dumps staged
- [ ] No `print()`, `breakpoint()` or commented-out experiments left behind
- [ ] Every new model has ACL rows and record rules
- [ ] Docs and `MEMORY.md` updated for this phase
- [ ] Commit message follows the convention
- [ ] No AI author or co-author attribution anywhere

---

## 7. Handling Mistakes

| Situation | Action |
|---|---|
| Bad message, not yet pushed | `git commit --amend` |
| Bad message, already pushed | Leave it. Rewriting shared history is worse than an imperfect message |
| Secret committed but not pushed | `git reset --soft HEAD~1`, remove it, recommit |
| Secret already pushed | **Rotate the secret immediately**, then purge from history and force-push. Rotation first — the credential is compromised the moment it is public |
| Broken `main` | Fix forward with a `fix:` commit. Revert only if the breakage is large |

---

## 8. Tagging

Tag at meaningful milestones so a working state can always be recovered:

```bash
git tag -a v0.1.0-phase1 -m "Phase 1: Docker foundation and module skeleton"
git push origin v0.1.0-phase1
```

Version scheme mirrors the Odoo module version, `18.0.<phase>.<minor>.<patch>`,
declared in `__manifest__.py` and bumped each phase.
