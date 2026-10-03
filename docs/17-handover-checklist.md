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
| L1 | Executive Dashboard renders the full-span 100k-row window in ~3.8 s, against a 2 s target | The **production** side no longer reads `fmes.production.report` — `_fetch_production_rows` now aggregates `fmes.production.entry` directly (mentor Round 2), dropping that fetch from 1.77 s to 0.57 s. The remaining cost is `fmes.utilization.report`, which is still an `_auto = False` SQL view FULL OUTER JOINing the entry table against the downtime-event table (2.11 s at full span) and so cannot be replaced by a single `_read_group` the way the production path could | **Partly resolved.** All KPI figures are unchanged (verified bit-identical for every KPI tile; series agree to <=9.3e-15 relative, i.e. float64 accumulation order only) and normal windows (30/90/180-day) now render in 1.37-1.49 s, inside the budget. Remaining fix path, unchanged and still open: give `_fetch_utilization_rows` its own two-source `_read_group` merge, or promote `fmes.utilization.report` to a cron-refreshed materialised view |
| L2 | ~~No per-operator PIN on the shop-floor terminal~~ — resolved | Individual Odoo logins remain the authentication (Phase 4 finding 2, assumption A16); a PIN **re-authentication gate** was added on top (mentor Round 2) using Odoo's own native `hr.employee.pin` — no custom PIN field, no second credential store, and the gate only ever accepts the PIN of the logged-in account (cannot switch operator). | **Resolved.** `/fmes/terminal/pin_verify` checks only the caller's own employee PIN (via sudo to read the group-restricted field), clears the attempt counter on success, limits wrong attempts to 5 per session, and the terminal shows a keypad gate on load. If no PIN is provisioned, the gate closes with a visible advisory rather than locking the operator out; PINs are set on the standard Odoo employee form. |
| L3 | `spreadsheet_dashboard` self-service boards were not built | Hand-authoring the underlying o-spreadsheet JSON reliably without the actual Spreadsheet editor UI was judged too fragile — a broken board is worse than none (Phase 10, deliberately deferred) | Deferred. Every pivot/graph view the boards would have wrapped already exists; a Plant Manager can build a real board directly from any of them through Odoo's own Spreadsheet app once real data exists |
| L4 | No browser was available in this development environment to visually verify any OWL/portal screen's actual render (terminal, scheduling board, dashboards, alert center, portal pages) | Environment constraint, present from Phase 10 onward | Mitigated, not eliminated: every screen verified by XML well-formedness, JS syntax checks, pattern-matching against Odoo's own native components, and full backend/HTTP-level tests (`HttpCase`, `odoo shell`). Pixel-level visual confirmation is the one thing not independently done — recommend a manual click-through before go-live |
| L5 | A Supervisor can delete a `maintenance.equipment` record; an Operator can write/delete their own `maintenance.request` | Both come from native Odoo group implications (`group_equipment_manager`, `base.group_user`'s own "own requests" rule) that would need editing native Odoo records to narrow, this late in the project, for a low-severity capability | Reviewed and accepted (Phase 14 finding 2), not a gap — documented here so it isn't rediscovered as a surprise during a future audit |
| L6 | Critical-alert escalation window is configurable per rule, defaulting to 30 minutes | Resolved — previously `ESCALATION_WINDOW_MINUTES`, a module-level constant in `services/alert_engine.py`, assumption `A55` | **Resolved.** `fmes.alert.rule.escalation_window_minutes` (positive, default 30) is read per alert, so one rule can escalate faster than another. Escalation now selects candidates without any global time cutoff and applies each alert's own rule window, because a single fixed cutoff would silently skip every alert on a rule configured with a longer window |
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
