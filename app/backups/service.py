"""Reads what the backup scripts left on disk, and runs one on demand.

The scripts in scripts/ stay the one way a backup gets made, so cron and the
Back up now button can't drift apart. Nothing here restores or hands out a dump:
a dump holds every password hash and customer, and restoring overwrites live data.
"""
import logging
import os
import re
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException

logger = logging.getLogger(__name__)

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backup_db.sh"
BACKUP_TIMEOUT_SECONDS = 300
OVERDUE_AFTER = timedelta(hours=26)

_running = threading.Lock()


def backup_dir() -> Path:
    return Path(os.getenv("BACKUP_DIR") or Path.home() / "zybrannox-backups")


def _modified_at(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return None


def _is_scheduled() -> bool:
    try:
        crontab = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return any(SCRIPT.name in line and not line.lstrip().startswith("#") for line in crontab.stdout.splitlines())


def _on_separate_disk(folder: Path) -> bool:
    try:
        return folder.stat().st_dev != Path.cwd().stat().st_dev
    except OSError:
        return False


def status() -> dict:
    folder = backup_dir()
    dumps = sorted(
        ((path.stat().st_mtime, path.stat().st_size) for path in folder.glob("billing-*.dump")),
        reverse=True,
    )
    last_at = datetime.fromtimestamp(dumps[0][0], timezone.utc) if dumps else None

    check_file = folder / ".last_restore_check"
    check_at = _modified_at(check_file)

    return {
        "last_backup_at": last_at,
        "last_backup_size_bytes": dumps[0][1] if dumps else None,
        "backup_count": len(dumps),
        "total_size_bytes": sum(size for _, size in dumps),
        "overdue": last_at is None or datetime.now(timezone.utc) - last_at > OVERDUE_AFTER,
        "scheduled": _is_scheduled(),
        "on_separate_disk": _on_separate_disk(folder),
        "last_restore_check_at": check_at,
        "last_restore_check_matched": check_file.read_text().strip() == "match" if check_at else None,
        "uploads_last_copied_at": _modified_at(folder / ".last_uploads_copy"),
    }


def run_backup() -> None:
    if not _running.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A backup is already running. Try again in a minute.")
    try:
        result = subprocess.run(
            [str(SCRIPT)],
            capture_output=True,
            text=True,
            timeout=BACKUP_TIMEOUT_SECONDS,
            env={**os.environ, "BACKUP_DIR": str(backup_dir())},
        )
        if result.returncode != 0:
            # The error can quote the connection string, so the password comes out first.
            logger.error("Backup failed: %s", re.sub(r"://([^:@/\s]+):[^@\s]+@", r"://\1:***@", result.stderr))
            raise HTTPException(status_code=500, detail="The backup failed. Your data is untouched; check the server log.")
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("Backup could not run: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="The backup failed. Your data is untouched; check the server log.")
    finally:
        _running.release()
