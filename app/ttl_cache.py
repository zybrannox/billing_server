"""A tiny in-process cache for read-heavy endpoints whose answer only changes
when someone writes (the admin dashboard, the delivery-notification bell that
polls on every admin page).

Entries live CACHE_TTL_SECONDS at most and the whole cache is cleared the
moment any state-changing request succeeds (see CacheInvalidationMiddleware),
so a user never sees a number older than their own last action. It is
per-process: with several workers another worker may serve data up to the TTL
old - fine for these endpoints, wrong for anything transactional.
"""
import os
import time
from threading import Lock
from typing import Any, Callable

CACHE_TTL_SECONDS = float(os.getenv("CACHE_TTL_SECONDS", "15"))

_entries: dict[Any, tuple[float, Any]] = {}
_lock = Lock()
# Bumped by clear(): a value computed before a write finished must not be
# stored after the write cleared the cache, or it would outlive the clear.
_generation = 0


def get_or_compute(key: Any, compute: Callable[[], Any], ttl: float | None = None) -> Any:
    ttl = CACHE_TTL_SECONDS if ttl is None else ttl
    if ttl <= 0:
        return compute()
    now = time.monotonic()
    with _lock:
        hit = _entries.get(key)
        if hit and hit[0] > now:
            return hit[1]
        generation = _generation
    value = compute()
    with _lock:
        if generation == _generation:
            _entries[key] = (now + ttl, value)
    return value


def clear() -> None:
    global _generation
    with _lock:
        _generation += 1
        _entries.clear()
