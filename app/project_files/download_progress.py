"""How far along each large download is, so the app can show "120 MB of 1 GB".

Those downloads belong to the browser's own download manager, so the page can't
see their bytes. This server can, and the page polls it. It counts bytes handed
to the connection, so it can run slightly ahead of what has actually arrived.

In memory, like chunked uploads (one process - see chunked.py). A restart only
loses the progress display; the download itself is unaffected.
"""
import time
from threading import Lock
from typing import Dict, Optional

# Long enough for any download to have finished and been read one last time.
_KEEP_SECONDS = 24 * 60 * 60

_entries: Dict[str, dict] = {}
_lock = Lock()


def begin(progress_id: str) -> None:
    """The request has arrived, but sending hasn't started (a zip is being built)."""
    with _lock:
        cutoff = time.time() - _KEEP_SECONDS
        for key in [k for k, e in _entries.items() if e["updated"] < cutoff]:
            del _entries[key]
        _entries[progress_id] = {"state": "preparing", "sent": 0, "total": None, "updated": time.time()}


def _change(progress_id: str, **fields) -> None:
    with _lock:
        entry = _entries.get(progress_id)
        if entry:
            entry.update(fields, updated=time.time())


def sending(progress_id: str, total: int, already_sent: int = 0) -> None:
    """`already_sent` is where a resumed download picks up from."""
    if progress_id not in _entries:
        begin(progress_id)
    _change(progress_id, state="sending", total=total, sent=already_sent)


def add(progress_id: str, count: int) -> None:
    with _lock:
        entry = _entries.get(progress_id)
        if entry:
            entry["sent"] += count
            entry["updated"] = time.time()


def finished(progress_id: str) -> None:
    _change(progress_id, state="done")


def stopped(progress_id: str) -> None:
    _change(progress_id, state="stopped")


def read(progress_id: str) -> Optional[dict]:
    with _lock:
        entry = _entries.get(progress_id)
        return {k: entry[k] for k in ("state", "sent", "total")} if entry else None
