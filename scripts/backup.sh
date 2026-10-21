#!/usr/bin/env bash
# Back up the CareTrip database to ./backups as a compressed custom-format dump, keeping the newest $KEEP.
#
#   scripts/backup.sh                 # uses the Compose db service
#   KEEP=30 scripts/backup.sh
#
# In production, point PGHOST/PGUSER/PGDATABASE at the managed database and run pg_dump directly with the same
# flags, then copy the file off the machine (object storage with versioning). A backup nobody restores is a hope:
# run scripts/restore.sh --check against each new dump.
set -euo pipefail

cd "$(dirname "$0")/.."
KEEP="${KEEP:-14}"
DB="${PGDATABASE:-caretrip}"
mkdir -p backups
file="backups/caretrip-$(date -u +%Y%m%dT%H%M%SZ).dump"

docker compose exec -T db pg_dump -U caretrip -d "$DB" --format=custom --compress=9 --no-owner > "$file.partial"
mv "$file.partial" "$file"
echo "Wrote $file ($(du -h "$file" | cut -f1))"

# Keep the newest $KEEP dumps.
ls -1t backups/caretrip-*.dump | tail -n "+$((KEEP + 1))" | while read -r old; do rm -f -- "$old"; echo "Removed $old"; done
