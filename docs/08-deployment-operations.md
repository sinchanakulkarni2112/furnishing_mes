# 08 — Deployment & Operations

Target: a **single on-premise server** in the customer's plant, running the stack
under Docker Compose. Sized for roughly 30 internal users and 10 shop-floor tablets.

> Most of this document is realised in **Phase 15**. It is specified here so that
> every earlier phase is built with these constraints in mind.

---

## 1. Server Requirements

| | Minimum | Recommended |
|---|---|---|
| CPU | 4 cores | 8 cores |
| RAM | 8 GB | 16 GB |
| Disk | 100 GB SSD | 250 GB SSD |
| OS | Ubuntu 22.04 LTS / Debian 12 | Same |
| Docker | Engine 24 + Compose v2 | Latest stable |
| Network | Static LAN IP | Static IP + internal DNS name |

Disk grows with the filestore (attachments, generated PDFs, equipment photos)
more than with the database. Budget roughly 20 GB per year at the expected volume.

---

## 2. Production Topology

```
   Shop-floor tablets          Office desktops
            │                        │
            └────────┬───────────────┘
                     ▼
        ┌────────────────────────────┐
        │  Nginx / Caddy (host)      │   TLS termination, HTTP→HTTPS,
        │  :80 → :443                │   websocket proxy for longpolling
        └────────────┬───────────────┘
                     ▼  127.0.0.1:8069
        ┌────────────────────────────────────────┐
        │  Docker: internal bridge network       │
        │   web (odoo:18.0, workers=4)           │
        │   db  (postgres:15, no published port) │
        └────────────────────────────────────────┘
                     │
              nightly backup → off-server storage
```

The reverse proxy runs **on the host**, not in the Compose stack, so TLS
certificates and the plant's existing web estate stay under the customer's normal
administration. `docker-compose.prod.yml` binds Odoo to `127.0.0.1:8069` so it is
never directly reachable from the LAN.

---

## 3. Production Overrides — `docker-compose.prod.yml`

Applied with:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

What it changes:

| Setting | Development | Production |
|---|---|---|
| Odoo port binding | `0.0.0.0:8069` | `127.0.0.1:8069` |
| `workers` | `0` (single process, debuggable) | `4` (see formula below) |
| `proxy_mode` | `False` | `True` |
| `log_level` | `debug` / `info` | `warn` |
| `list_db` | `False` | `False` |
| Image | `odoo:18.0` | pinned by digest, `odoo:18.0@sha256:...` |
| Restart policy | `unless-stopped` | `always` |
| Resource limits | none | CPU and memory limits set |
| Log driver | default | `json-file` with `max-size` and `max-file` rotation |
| Demo data | loaded | **never** — production installs with `--without-demo=all` |

**Worker formula.** `workers = (2 × CPU cores) + 1`, capped by RAM at roughly
600 MB per worker. On an 8-core / 16 GB server, `workers = 9` is safe;
`workers = 4` is a conservative starting point. Also set:

```ini
limit_memory_soft = 2147483648      # 2 GB
limit_memory_hard = 2684354560      # 2.5 GB
limit_time_cpu = 600
limit_time_real = 1200              # long report generation needs headroom
max_cron_threads = 2
```

`max_cron_threads` must be at least 2 — the backlog snapshot, carry-forward,
preventive-maintenance and alert crons all run overnight and would otherwise
serialise behind one another.

---

## 4. Reverse Proxy

A sample Nginx configuration ships in `deploy/nginx/furnishing_mes.conf`
(Phase 15). The essentials:

- Terminate TLS; redirect all HTTP to HTTPS
- Proxy `/` to `127.0.0.1:8069`
- Proxy `/websocket` to `127.0.0.1:8072` with `Upgrade`/`Connection` headers —
  without this, Odoo 18's longpolling and live updates silently fail
- Forward `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Real-IP` (required for
  `proxy_mode = True` to be meaningful)
- `client_max_body_size 100M` for XLSX imports and equipment photos
- `proxy_read_timeout 720s` for long report generation
- Enable gzip for text, JS, CSS and JSON

Certificates: Let's Encrypt if the server is reachable from the internet,
otherwise the customer's internal CA. Renewal is a host cron, outside Docker.

---

## 5. Backup and Recovery

**Targets:** RPO 24 hours, RTO 4 hours.

Two things must be backed up together, and they must be consistent with each
other: the **database** and the **filestore**. A database restored without its
matching filestore loses every attachment.

`scripts/backup.sh` (Phase 15):

```bash
#!/usr/bin/env bash
set -euo pipefail
STAMP=$(date +%Y%m%d_%H%M%S)
DEST=/var/backups/fmes
mkdir -p "$DEST"

docker compose exec -T db pg_dump -U odoo -Fc furnishing_mes \
  > "$DEST/db_$STAMP.dump"

# Volumes are prefixed with the Compose project name.
FILESTORE_VOLUME="${COMPOSE_PROJECT_NAME:-furnishing-mes}_fmes-web-data"
docker run --rm -v "$FILESTORE_VOLUME":/data -v "$DEST":/backup alpine \
  tar czf "/backup/filestore_$STAMP.tar.gz" -C /data .

find "$DEST" -type f -mtime +30 -delete
```

Schedule at 01:00 daily via host cron, **before** the overnight Odoo crons so the
backup captures a settled state. Copy off-server the same night — a backup on the
same disk as the database is not a backup.

Retention: 30 daily, 12 monthly, 3 yearly.

**Restore drill** (`scripts/restore.sh`, rehearsed in Phase 14):

```bash
docker compose stop web
docker compose exec -T db dropdb -U odoo furnishing_mes
docker compose exec -T db createdb -U odoo furnishing_mes
docker compose exec -T db pg_restore -U odoo -d furnishing_mes < db_YYYYMMDD.dump
docker run --rm -v furnishing-mes_fmes-web-data:/data -v /var/backups/fmes:/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/filestore_YYYYMMDD.tar.gz -C /data"
docker compose start web
```

Verify after every restore: record counts on `fmes_production_entry`, a PDF
report renders, and one attachment opens.

---

## 6. Upgrades

### Module upgrade (routine — after each phase)

```bash
./scripts/backup.sh
git pull origin main
docker compose exec web odoo -d furnishing_mes -u furnishing_mes --stop-after-init
docker compose restart web
```

Always take the backup first. Always test the same upgrade on a copy of
production data before running it on production.

### Odoo patch upgrade (18.0.x)

Pull the new image, restart, then upgrade `base` and the module. Odoo point
releases are backward-compatible; still, back up first.

### Odoo major upgrade (18 → 19)

Not routine. Requires reviewing every model extension and OWL component against
the new API, on a staging copy, before any production date is set. Budget it as a
project, not a maintenance window.

### Rollback

Because upgrades run schema migrations, rollback means **restore from backup**,
not `git revert`. This is why the pre-upgrade backup is mandatory rather than
advisory.

---

## 7. Monitoring

| What | How | Alert when |
|---|---|---|
| Container health | Compose healthchecks; `docker compose ps` | A container is not `healthy` |
| Odoo responsiveness | HTTP probe on `/web/health` | Non-200 for 2 minutes |
| Disk usage | Host monitoring | Above 80 % |
| Database size | `pg_database_size` | Growth deviates from trend |
| Backup success | Exit code of `backup.sh` written to a log | Non-zero, or no new file today |
| Cron execution | `ir.cron` last-run timestamps | A cron has not run in 24 hours |
| Error rate | `docker compose logs web \| grep ERROR` | Any new traceback |

Odoo's own **Settings → Technical → Scheduled Actions** page is the first place
to look when something automated has not happened.

---

## 8. Operational Runbook

| Situation | Action |
|---|---|
| Odoo will not start | `docker compose logs web`; the traceback names the failing module or config line. Most often a syntax error in a newly added XML file |
| Login page hangs | Check `db` is healthy; check disk is not full |
| Live updates stopped working | The reverse proxy is not forwarding `/websocket` to port 8072 |
| A cron did not run | Technical → Scheduled Actions; check it is active and `max_cron_threads ≥ 2` |
| Reports time out | Raise `limit_time_real`; narrow the report's date range; check the SQL-view indexes |
| A user reports "record does not exist" | Almost always a record rule doing its job. Verify against the permission matrix before changing anything |
| Disk filling | Old report attachments; add an `ir.attachment` cleanup cron for generated reports older than 90 days |
| Emergency stop | `docker compose stop web` leaves the database intact and running |

---

## 9. Go-Live Checklist

- [ ] Server provisioned, Docker installed, firewall allows only 80/443 from the LAN
- [ ] `.env` created with strong, unique `POSTGRES_PASSWORD` and `ADMIN_PASSWD`
- [ ] Production compose file in use; Odoo bound to `127.0.0.1`
- [ ] Database initialised with `--without-demo=all` — **no demo data in production**
- [ ] Reverse proxy configured, TLS valid, `/websocket` proxied
- [ ] Real master data loaded: departments, shifts, machines, equipment, capacity matrix
- [ ] Real users created and assigned to the correct groups; admin password changed
- [ ] Portal customers invited
- [ ] Alert rules reviewed and thresholds tuned with the plant manager
- [ ] Report schedules configured with real recipients
- [ ] Backup script installed, scheduled, and a restore rehearsed successfully
- [ ] Monitoring in place
- [ ] Operators trained on the terminal; supervisors trained on approvals
- [ ] Known-limitations register handed over
