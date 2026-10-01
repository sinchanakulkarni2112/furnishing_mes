#!/usr/bin/env bash
# Furnishing MES — production restore.
#
# Restores a database dump and its matching filestore archive produced by
# scripts/backup.sh. See docs/08-deployment-operations.md section 5.
#
# Usage:  ./scripts/restore.sh <db_dump_path> <filestore_tar_path>
# Example: ./scripts/restore.sh /var/backups/fmes/db_20260907_010000.dump \
#                                /var/backups/fmes/filestore_20260907_010000.tar.gz
#
# DESTRUCTIVE: drops and recreates the furnishing_mes database and replaces
# the entire filestore volume. Run against production only as a deliberate
# recovery action, never routinely.

set -euo pipefail

if [ $# -ne 2 ]; then
  echo "Usage: $0 <db_dump_path> <filestore_tar_path>" >&2
  exit 1
fi

DB_DUMP=$1
FILESTORE_TAR=$2
FILESTORE_VOLUME="${COMPOSE_PROJECT_NAME:-furnishing-mes}_fmes-web-data"

for f in "$DB_DUMP" "$FILESTORE_TAR"; do
  if [ ! -f "$f" ]; then
    echo "Not found: $f" >&2
    exit 1
  fi
done

echo "Restoring from:"
echo "  db:        $DB_DUMP"
echo "  filestore: $FILESTORE_TAR"
echo "  volume:    $FILESTORE_VOLUME"
read -r -p "This will DESTROY the current furnishing_mes database and filestore. Type 'yes' to continue: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "Aborted."
  exit 1
fi

docker compose stop web

docker compose exec -T db dropdb -U odoo --if-exists furnishing_mes
docker compose exec -T db createdb -U odoo furnishing_mes
docker compose exec -T db pg_restore -U odoo -d furnishing_mes < "$DB_DUMP"

docker run --rm -v "$FILESTORE_VOLUME":/data -v "$(cd "$(dirname "$FILESTORE_TAR")" && pwd)":/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/$(basename "$FILESTORE_TAR") -C /data"

docker compose start web

echo "Restore complete. Verify: record counts on fmes_production_entry, a PDF report renders, one attachment opens."
