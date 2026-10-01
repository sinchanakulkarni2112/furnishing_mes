#!/usr/bin/env bash
# Furnishing MES — production backup.
#
# Dumps the database and the filestore together so a restore is always from
# one consistent pair. See docs/08-deployment-operations.md section 5.
#
# Usage:  ./scripts/backup.sh
# Schedule at 01:00 daily via host cron, before the overnight Odoo crons so
# the backup captures a settled state:
#
#   0 1 * * *  cd /opt/furnishing_mes && ./scripts/backup.sh >> /var/log/fmes-backup.log 2>&1
#
# Copy $DEST off-server the same night — a backup on the same disk as the
# database is not a backup.

set -euo pipefail

STAMP=$(date +%Y%m%d_%H%M%S)
DEST=${FMES_BACKUP_DIR:-/var/backups/fmes}
mkdir -p "$DEST"

docker compose exec -T db pg_dump -U odoo -Fc furnishing_mes \
  > "$DEST/db_$STAMP.dump"

# Volumes are prefixed with the Compose project name (docker-compose.yml
# "name:"), not the directory name — must match or this silently backs up
# an empty volume.
FILESTORE_VOLUME="${COMPOSE_PROJECT_NAME:-furnishing-mes}_fmes-web-data"
docker run --rm -v "$FILESTORE_VOLUME":/data -v "$DEST":/backup alpine \
  tar czf "/backup/filestore_$STAMP.tar.gz" -C /data .

# Retention: 30 days locally. Longer-term (12 monthly, 3 yearly per docs/08)
# is a policy on the off-server copy, not this script's concern.
find "$DEST" -maxdepth 1 -type f -name '*.dump' -mtime +30 -delete
find "$DEST" -maxdepth 1 -type f -name '*.tar.gz' -mtime +30 -delete

echo "Backup complete: $DEST/db_$STAMP.dump, $DEST/filestore_$STAMP.tar.gz"
