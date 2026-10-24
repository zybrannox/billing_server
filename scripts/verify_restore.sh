#!/usr/bin/env bash
# Prove the newest backup actually restores: load it into a throw-away
# database and compare its table row counts with the live database.
#
#   scripts/verify_restore.sh [dump-file]
#
# Never touches the live database (read-only counts) and always drops the
# scratch database it creates.
set -euo pipefail

cd "$(dirname "$0")/.."
if [ -z "${DATABASE_URL:-}" ] && [ -f .env ]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2-)"
fi
: "${DATABASE_URL:?DATABASE_URL is not set}"
for tool in pg_restore psql createdb dropdb; do
  command -v "$tool" >/dev/null || { echo "$tool not found - install the PostgreSQL client tools" >&2; exit 1; }
done

BACKUP_DIR="${BACKUP_DIR:-$HOME/zybrannox-backups}"
DUMP="${1:-$(ls -t "$BACKUP_DIR"/billing-*.dump 2>/dev/null | head -1)}"
[ -n "$DUMP" ] && [ -f "$DUMP" ] || { echo "no dump found (looked in $BACKUP_DIR)" >&2; exit 1; }

PG_URL="${DATABASE_URL/postgresql+psycopg/postgresql}"
SCRATCH="zyb_restore_check_$$"
# Same server, scratch database name: strip the db name from the URL path.
SERVER_URL="${PG_URL%/*}"
trap 'dropdb --if-exists --maintenance-db="$SERVER_URL/postgres" "$SCRATCH" >/dev/null 2>&1 || true' EXIT

createdb --maintenance-db="$SERVER_URL/postgres" "$SCRATCH"
pg_restore --no-owner --dbname="$SERVER_URL/$SCRATCH" "$DUMP"

exact_counts() {
  local url="$1" tables
  tables=$(psql "$url" -Atc "select tablename from pg_tables where schemaname='public' order by 1")
  for t in $tables; do echo "$t=$(psql "$url" -Atc "select count(*) from \"$t\"")"; done
}
LIVE="$(exact_counts "$PG_URL")"
RESTORED="$(exact_counts "$SERVER_URL/$SCRATCH")"

echo "restored from: $DUMP"
if diff <(echo "$LIVE") <(echo "$RESTORED") >/dev/null; then
  echo "OK - every table's row count matches the live database"
else
  echo "Row counts differ (expected if data changed since the backup):"
  diff <(echo "$LIVE") <(echo "$RESTORED") || true
fi
