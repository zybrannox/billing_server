"""Read-only facts about the machine the backend runs on.

Everything here is cheap or cached, and none of it runs shell commands or
reads files outside the app's own data folders. Slow work (walking the uploads
folder, asking Postgres for table sizes) happens in a background job and the
request just reads the last result - a health screen that itself causes lag
would be worse than none.
"""
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

import psutil
from sqlalchemy import text

from app.database import engine

_SNAPSHOT_TTL_SECONDS = 5

# What a process is, for people who don't know process names. Only ever the
# role label and numbers leave the server - never command lines or paths.
_ROLE_BACKEND = "This app (backend)"
_ROLE_DATABASE = "Database (Postgres)"
_ROLE_WEB = "Web server"
_ROLE_TUNNEL = "Public tunnel (cloudflared)"


def _role_of(proc: psutil.Process, name: str) -> str | None:
    lowered = name.lower()
    if proc.pid == os.getpid():
        return _ROLE_BACKEND
    if lowered.startswith("postgres"):
        return _ROLE_DATABASE
    if lowered.startswith("cloudflared"):
        return _ROLE_TUNNEL
    if lowered in ("node", "serve") or lowered.startswith("python"):
        try:
            cmdline = " ".join(proc.cmdline()).lower()
        except (psutil.Error, OSError):
            return None
        if lowered.startswith("python") and ("uvicorn" in cmdline and "app.main" in cmdline):
            return _ROLE_BACKEND
        if lowered in ("node", "serve") and "serve" in cmdline:
            return _ROLE_WEB
    return None


def _megabytes(n: float) -> float:
    return round(n / (1024 * 1024), 1)


def machine_snapshot() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    cores = psutil.cpu_count(logical=True) or 1
    load1 = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
    disk = psutil.disk_usage(str(_data_root()))
    return {
        "memory_total_mb": _megabytes(memory.total),
        "memory_available_mb": _megabytes(memory.available),
        "memory_available_pct": round(memory.available / memory.total * 100, 1),
        "swap_used_mb": _megabytes(swap.used),
        "cpu_cores": cores,
        "load_per_core": round(load1 / cores, 2),
        "disk_total_gb": round(disk.total / 1024**3, 1),
        "disk_free_gb": round(disk.free / 1024**3, 1),
        "disk_free_pct": round(disk.free / disk.total * 100, 1),
        "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
    }


def process_snapshot(top_other: int = 5) -> dict[str, Any]:
    """Memory per app component, and the biggest other processes on the box."""
    roles: dict[str, dict[str, Any]] = {}
    others: list[tuple[float, str]] = []
    for proc in psutil.process_iter(["name", "memory_info"]):
        try:
            info = proc.info
            name = info.get("name") or "?"
            role = _role_of(proc, name)
            memory = info.get("memory_info")
            if role:
                entry = roles.setdefault(role, {"role": role, "processes": 0, "rss_bytes": 0, "unreadable": 0})
                entry["processes"] += 1
                if memory:
                    entry["rss_bytes"] += memory.rss
                else:
                    # e.g. Postgres running as another user: visible, not measurable.
                    entry["unreadable"] += 1
            elif memory:
                others.append((memory.rss, name))
        except (psutil.Error, OSError):
            continue

    total = psutil.virtual_memory().total
    components = []
    for entry in roles.values():
        components.append(
            {
                "role": entry["role"],
                "processes": entry["processes"],
                "memory_mb": _megabytes(entry["rss_bytes"]),
                "memory_pct": round(entry["rss_bytes"] / total * 100, 1),
                # Postgres workers share memory; summing each one's resident
                # size counts the shared part several times.
                "approximate": entry["role"] == _ROLE_DATABASE and entry["processes"] > 1,
                # False when the OS won't tell us (the process belongs to another user).
                "memory_known": entry["unreadable"] < entry["processes"],
            }
        )
    components.sort(key=lambda c: c["memory_mb"], reverse=True)

    merged: dict[str, float] = {}
    for rss, name in others:
        merged[name] = merged.get(name, 0) + rss
    top = sorted(merged.items(), key=lambda kv: kv[1], reverse=True)[:top_other]
    return {
        "components": components,
        "other_top": [{"name": n, "memory_mb": _megabytes(b), "memory_pct": round(b / total * 100, 1)} for n, b in top],
    }


def database_pool() -> dict[str, int] | None:
    pool = engine.pool
    try:
        return {
            "size": pool.size() + max(0, getattr(pool, "_max_overflow", 0)),
            "in_use": pool.checkedout(),
        }
    except AttributeError:  # SQLite's pool has no such counters
        return None


# --- cached snapshot (shared by every poller) --------------------------------

_cache_lock = Lock()
_cache: dict[str, Any] = {"at": 0.0, "value": None}


def live_snapshot() -> dict[str, Any]:
    """Machine + processes + pool, recomputed at most every few seconds no
    matter how many admins have the screen open."""
    with _cache_lock:
        if _cache["value"] is not None and time.monotonic() - _cache["at"] < _SNAPSHOT_TTL_SECONDS:
            return _cache["value"]
        value = {"machine": machine_snapshot(), "processes": process_snapshot(), "pool": database_pool()}
        _cache.update(at=time.monotonic(), value=value)
        return value


# --- storage (background-refreshed) -----------------------------------------

def _uploads_dir() -> Path:
    from app.project_files.service import UPLOAD_DIR

    return Path(UPLOAD_DIR).resolve()


def _data_root() -> Path:
    try:
        return _uploads_dir() if _uploads_dir().exists() else Path.cwd()
    except Exception:
        return Path.cwd()


def _scan(root: Path, deadline: float) -> tuple[int, int, bool]:
    """(bytes, files, complete) under root - iterative, never follows symlinks,
    gives up (marking the result partial) when the time budget runs out."""
    total = files = 0
    stack = [root]
    while stack:
        if time.monotonic() > deadline:
            return total, files, False
        try:
            with os.scandir(stack.pop()) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                            files += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return total, files, True


@dataclass
class StorageReport:
    computed_at: float = 0.0
    folders: list[dict[str, Any]] = field(default_factory=list)
    database: dict[str, Any] | None = None
    complete: bool = True


_storage_lock = Lock()
_storage: StorageReport | None = None
_refreshing = False
STORAGE_TIME_BUDGET_SECONDS = float(os.getenv("STORAGE_SCAN_BUDGET_SECONDS", "30"))


def _database_sizes() -> dict[str, Any] | None:
    if engine.dialect.name != "postgresql":
        return None
    with engine.connect() as conn:
        total = conn.execute(text("select pg_database_size(current_database())")).scalar_one()
        tables = conn.execute(
            text(
                "select relname, pg_total_relation_size(c.oid) from pg_class c "
                "join pg_namespace n on n.oid = c.relnamespace "
                "where c.relkind = 'r' and n.nspname = 'public' "
                "order by 2 desc limit 6"
            )
        ).all()
    return {
        "total_mb": _megabytes(total),
        "largest_tables": [{"name": name, "size_mb": _megabytes(size)} for name, size in tables],
    }


def refresh_storage() -> StorageReport:
    """Walk the app's data folders and ask Postgres for its size. Called from
    a scheduler thread - never from a request."""
    global _storage, _refreshing
    with _storage_lock:
        if _refreshing:
            return _storage or StorageReport()
        _refreshing = True
    try:
        deadline = time.monotonic() + STORAGE_TIME_BUDGET_SECONDS
        uploads = _uploads_dir()
        thumbs, temp = uploads / "thumbnails", uploads / ".chunked"
        up_total, up_files, up_done = _scan(uploads, deadline)
        th_total, th_files, th_done = _scan(thumbs, deadline) if thumbs.exists() else (0, 0, True)
        tmp_total, tmp_files, tmp_done = _scan(temp, deadline) if temp.exists() else (0, 0, True)
        folders = [
            {"label": "Customer files", "size_mb": _megabytes(max(0, up_total - th_total - tmp_total)),
             "files": max(0, up_files - th_files - tmp_files)},
            {"label": "Image previews (thumbnails)", "size_mb": _megabytes(th_total), "files": th_files},
            {"label": "Unfinished uploads", "size_mb": _megabytes(tmp_total), "files": tmp_files},
        ]
        backups = Path(os.getenv("BACKUP_DIR", str(Path.home() / "zybrannox-backups")))
        if backups.exists():
            b_total, b_files, b_done = _scan(backups, deadline)
            folders.append({"label": "Database backups", "size_mb": _megabytes(b_total), "files": b_files})
            up_done = up_done and b_done
        try:
            database = _database_sizes()
        except Exception:
            database = None
        report = StorageReport(
            computed_at=time.time(), folders=folders, database=database,
            complete=up_done and th_done and tmp_done,
        )
        with _storage_lock:
            _storage = report
        return report
    finally:
        with _storage_lock:
            _refreshing = False


def storage_report() -> tuple[StorageReport | None, bool]:
    """The last computed storage report and whether a refresh is running."""
    with _storage_lock:
        return _storage, _refreshing
