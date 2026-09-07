# 17 — Handover Checklist & Known-Limitations Register

Two parts: what to confirm before go-live, and a full, honest list of the
project's known gaps — recorded so nobody discovers them by surprise later.

---

## Part A — Go-Live Checklist

This extends the checklist already in `docs/08-deployment-operations.md`
section 9 with what Phase 15 specifically added. Do both.

**From docs/08 section 9** (infrastructure and data):
- [ ] Server provisioned, Docker installed, firewall allows only 80/443 from the LAN
- [ ] `.env` created with strong, unique `POSTGRES_PASSWORD`
- [ ] `config/odoo.prod.conf` created from `config/odoo.prod.conf.example` with a
      real, generated `admin_passwd` (git-ignored — never commit it)
- [ ] Deployed with `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`;
      Odoo bound to `127.0.0.1` only (confirm: `curl` from another host on the
      LAN gets no response on 8069/8072)
- [ ] Database initialised with `make init-prod` (`--without-demo=all`) —
      **no demo data in production**
- [ ] Reverse proxy configured from `deploy/nginx/furnishing_mes.conf`, TLS
      valid, `/websocket` proxied (confirm: Alert Center badge / live status
      board actually updates without a manual refresh)
- [ ] Real master data loaded per `docs/16-administrator-guide.md` section 1
- [ ] Real users created and assigned to the correct groups; default admin
      password changed
- [ ] Portal customers invited via Grant Portal Access (not seeded demo logins)
- [ ] Alert rules reviewed and thresholds tuned with the plant manager
- [ ] Report schedules configured with real recipients
- [ ] Monitoring in place (`/web/health` probe, disk, backup-success check)
- [ ] Operators trained on the terminal; supervisors trained on approvals

**Added by Phase 15:**
- [ ] `scripts/backup.sh` scheduled via host cron (01:00 daily, before the
      overnight Odoo crons); confirmed to actually produce a dump and a
      filestore archive (`FMES_BACKUP_DIR` writable, off-server copy target
      configured)
- [ ] `scripts/restore.sh` rehearsed at least once against this specific
      deployment (not just against the dev stack) — record counts on
      `fmes_production_entry`, a PDF report renders, one attachment opens,
      per the script's own closing check
- [ ] `docker-compose.prod.yml` resource limits (`cpus`/`memory`) sized to the
      actual server, not left at the 4-core/16GB default in this repo
- [ ] `workers` in `config/odoo.prod.conf` set from `(2 × cores) + 1`, capped
      by RAM, for the real server — not left at the conservative default of 4
- [ ] Known-limitations register below reviewed with the plant manager and
      customer sign-off obtained on anything that affects their decision to
      go live

## Part B — Known-Limitations Register

One row per real, currently-open limitation found across all 15 phases (source:
`docs/06-build-plan.md`'s own "Deviations and findings" per phase, and
`MEMORY.md`). Nothing here is invented for this document — every row traces
to a specific phase's own honest finding.

| # | Limitation | Why | Status |
|---|---|---|---|
| L1 | Executive Dashboard measures ~5.0 s at 100k+ row volume, against a 2 s target | `fmes.production.report`'s SQL view aggregates at full grain before any date filter can be pushed down — a Postgres planner limitation of the view's own structure, not a missing index (Phase 14 finding 1) | Deferred by design. Fix path documented: promote the view to a cron-refreshed materialised view, or have the dashboard read `fmes.production.entry` directly at its own coarser grain. Not attempted — the correctness risk of touching a KPI-critical, already-tested component outweighed the gain this late in the project |
| L2 | No per-operator PIN login on the shop-floor terminal | Individual Odoo logins give a real audit trail and avoid building a second authentication mechanism (Phase 4 finding 2, assumption A16) | Open question `Q12` in `docs/15-open-questions-and-assumptions.md` — a PIN layer can be added on top of the existing login without changing the domain model, if the plant wants shared-tablet sessions |
| L3 | `spreadsheet_dashboard` self-service boards were not built | Hand-authoring the underlying o-spreadsheet JSON reliably without the actual Spreadsheet editor UI was judged too fragile — a broken board is worse than none (Phase 10, deliberately deferred) | Deferred. Every pivot/graph view the boards would have wrapped already exists; a Plant Manager can build a real board directly from any of them through Odoo's own Spreadsheet app once real data exists |
| L4 | No browser was available in this development environment to visually verify any OWL/portal screen's actual render (terminal, scheduling board, dashboards, alert center, portal pages) | Environment constraint, present from Phase 10 onward | Mitigated, not eliminated: every screen verified by XML well-formedness, JS syntax checks, pattern-matching against Odoo's own native components, and full backend/HTTP-level tests (`HttpCase`, `odoo shell`). Pixel-level visual confirmation is the one thing not independently done — recommend a manual click-through before go-live |
| L5 | A Supervisor can delete a `maintenance.equipment` record; an Operator can write/delete their own `maintenance.request` | Both come from native Odoo group implications (`group_equipment_manager`, `base.group_user`'s own "own requests" rule) that would need editing native Odoo records to narrow, this late in the project, for a low-severity capability | Reviewed and accepted (Phase 14 finding 2), not a gap — documented here so it isn't rediscovered as a surprise during a future audit |
| L6 | Critical-alert escalation window (30 minutes) is a fixed constant, not configurable per rule | `ESCALATION_WINDOW_MINUTES` in `services/alert_engine.py`, assumption `A55` | Not built as a per-rule setting; would be a small, well-scoped addition if a plant needs a different window |
| L7 | ERP 10.8 connector is not built | Deferred by customer decision — see `docs/09-erp-integration-roadmap.md` | The seam (`fmes.erp.sync.mixin`, `fmes.sync.log`, the abstract adapter) is built and dormant as of this phase's own readiness review. Delivery plan estimates ~7.5 weeks (stages I1-I7) once ERP sandbox access is granted — see docs/09 section 6 |
| L8 | ERP field-mapping table is an empty skeleton | Cannot be finalised without real ERP 10.8 schema access, which this project does not have | Genuinely blocked on external access, not something a default can stand in for (docs/09 section 2.3) |
| L9 | The sync mixin (`fmes.erp.sync.mixin`) is not yet inherited into `res.partner`, `product.template`, `mrp.bom`, `sale.order`, or `mrp.production` | Adding five unused columns to core, widely-used tables ahead of an actual connector would be premature schema (docs/09 section 3.2) | Deliberately deferred to stage I2 of the ERP delivery plan — a one-line-per-model change once the connector is authorised |
| L10 | `fmes.support.ticket` / Grant Portal Access is the only portal-provisioning path documented; no bulk portal-invite tool exists | Not requested; Odoo's native per-contact invite was judged sufficient for the expected customer count | If the plant onboards many customers at once, a small bulk-invite script would be a reasonable, low-risk future addition |

**On Docker + Git Bash on Windows (operational note, not a product limitation):**
the first `docker pull` of an image not yet cached locally (e.g. `alpine`, used
by `scripts/backup.sh`/`restore.sh`) can fail from a Git Bash shell with
`error getting credentials - err: exec: "docker-credential-desktop": executable
file not found in %PATH%` — a PATH-translation quirk between MSYS's POSIX-style
`PATH` and the Windows `docker.exe` binary's credential-helper lookup, not a
script bug. Run the first pull of any new image from PowerShell or cmd.exe once
(`docker pull alpine`), after which the image is cached locally and every
subsequent `docker run`/`docker compose` invocation — from either shell — uses
the local copy without needing the credential helper again.
