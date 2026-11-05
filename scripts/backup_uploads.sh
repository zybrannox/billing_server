#!/usr/bin/env bash
# Copy uploaded files to BACKUP_DIR/uploads. backup_db.sh only covers the
# database, and the files are the part that can't be recreated. Run it from
# cron/launchd alongside that script:
#
#   30 2 * * *  /path/to/billing_server/scripts/backup_uploads.sh
#
# Adds and updates, never removes: a file later deleted from uploads/ (the bin
# expiring, or the retention job) stays in the backup. Point BACKUP_DIR at
# another disk: a copy on the same drive doesn't survive that drive failing.
set -euo pipefail

cd "$(dirname "$0")/.."
BACKUP_DIR="${BACKUP_DIR:-$HOME/zybrannox-backups}"
UPLOADS_DIR="${UPLOADS_DIR:-uploads}"
[ -d "$UPLOADS_DIR" ] || { echo "no uploads folder at $UPLOADS_DIR"; exit 1; }

mkdir -p "$BACKUP_DIR/uploads"
chmod 700 "$BACKUP_DIR"
rsync -a "$UPLOADS_DIR/" "$BACKUP_DIR/uploads/"
echo "copied $UPLOADS_DIR to $BACKUP_DIR/uploads ($(du -sh "$BACKUP_DIR/uploads" | cut -f1))"
