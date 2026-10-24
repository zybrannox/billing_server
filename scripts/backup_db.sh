#!/usr/bin/env bash
# Dump the production database (custom format, compressed) to BACKUP_DIR and
# prune dumps older than BACKUP_KEEP_DAYS. Run it from cron/launchd:
#
#   0 2 * * *  /path/to/billing_server/scripts/backup_db.sh
#
# Needs pg_dump on PATH and DATABASE_URL (read from .env if not set). A backup
# you have never restored is only a hope - run scripts/verify_restore.sh
# regularly (it restores the newest dump into a throw-away database and checks
# the row counts).
set -euo pipefail

cd "$(dirname "$0")/.."
if [ -z "${DATABASE_URL:-}" ] && [ -f .env ]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2-)"
fi
: "${DATABASE_URL:?DATABASE_URL is not set}"
command -v pg_dump >/dev/null || { echo "pg_dump not found - install the PostgreSQL client tools" >&2; exit 1; }

BACKUP_DIR="${BACKUP_DIR:-$HOME/zybrannox-backups}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# SQLAlchemy URLs carry a driver suffix ("postgresql+psycopg://") libpq rejects.
PG_URL="${DATABASE_URL/postgresql+psycopg/postgresql}"
OUT="$BACKUP_DIR/billing-$(date +%Y%m%d-%H%M%S).dump"

umask 077
pg_dump --format=custom --no-owner --file="$OUT" "$PG_URL"
echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"

find "$BACKUP_DIR" -name 'billing-*.dump' -mtime "+$BACKUP_KEEP_DAYS" -delete
