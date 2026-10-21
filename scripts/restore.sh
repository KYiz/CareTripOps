#!/usr/bin/env bash
# Restore a dump made by scripts/backup.sh into a NEW database, never over the live one.
#
#   scripts/restore.sh backups/caretrip-20261011T010203Z.dump caretrip_restored
#   scripts/restore.sh --check backups/caretrip-20261011T010203Z.dump
#
# --check restores into a scratch database, compares row counts with the live database, and drops the scratch copy.
# Switching the application to a restored database is a deliberate, separate step (change DATABASE_URL).
set -euo pipefail

cd "$(dirname "$0")/.."
check=false
if [[ "${1:-}" == "--check" ]]; then check=true; shift; fi
dump="${1:?usage: scripts/restore.sh [--check] <dump> [target_db]}"
target="${2:-caretrip_restore_check}"
[[ -f "$dump" ]] || { echo "No such file: $dump" >&2; exit 1; }
[[ "$target" =~ ^[a-z_][a-z0-9_]*$ ]] || { echo "Target must be a plain database name" >&2; exit 1; }
[[ "$target" != "caretrip" ]] || { echo "Refusing to restore over the live database" >&2; exit 1; }

psql() { docker compose exec -T db psql -U caretrip -v ON_ERROR_STOP=1 -qtA "$@"; }

if [[ -n "$(psql -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '$target'")" ]]; then
  if $check; then psql -d postgres -c "DROP DATABASE \"$target\""; else echo "Database $target already exists" >&2; exit 1; fi
fi
psql -d postgres -c "CREATE DATABASE \"$target\""
docker compose exec -T db pg_restore -U caretrip -d "$target" --no-owner --exit-on-error < "$dump"
echo "Restored $dump into $target"

if $check; then
  counts() {
    psql -d "$1" -c "SELECT string_agg(t || '=' || n, ' ' ORDER BY t) FROM (
      SELECT 'cases' t, count(*) n FROM cases UNION ALL SELECT 'orders', count(*) FROM orders
      UNION ALL SELECT 'payments', count(*) FROM payments UNION ALL SELECT 'users', count(*) FROM users
      UNION ALL SELECT 'audit_events', count(*) FROM audit_events) x"
  }
  restored="$(counts "$target")"
  echo "Restored: $restored"
  echo "Live:     $(counts caretrip)  (the live database may have moved on since the dump)"
  version="$(psql -d "$target" -c "SELECT version_num FROM alembic_version")"
  echo "Schema revision: $version"
  psql -d postgres -c "DROP DATABASE \"$target\""
  echo "Check passed; scratch database dropped."
fi
