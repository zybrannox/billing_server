"""Request timing, kept cheap and bounded.

One pure-ASGI middleware records every request's route template, duration and
status into per-minute histograms. Memory is constant (routes x buckets x
minutes - no per-request samples), the lock is held for a few dict updates, and
any failure in here is swallowed: monitoring must never break a request.
"""
import time
from bisect import bisect_left
from threading import Lock
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Upper edges (ms) of the latency buckets; the last bucket is "slower than all".
BUCKET_EDGES_MS = (5, 10, 25, 50, 100, 200, 400, 800, 1600, 3200, 6400)
WINDOW_MINUTES = 60
# Transfers are long by nature (a 500 MB upload takes minutes); counting them
# as "slow requests" would hide real problems and cry wolf constantly.
EXCLUDED_PREFIXES = ("/files", "/system-health")


class _RouteStats:
    __slots__ = ("count", "errors", "total_ms", "histogram")

    def __init__(self) -> None:
        self.count = 0
        self.errors = 0
        self.total_ms = 0.0
        self.histogram = [0] * (len(BUCKET_EDGES_MS) + 1)


def percentile_ms(histogram: list[int], pct: float) -> float | None:
    """Approximate percentile: the upper edge of the bucket containing it."""
    total = sum(histogram)
    if total == 0:
        return None
    target = total * pct / 100
    seen = 0
    for index, n in enumerate(histogram):
        seen += n
        if seen >= target:
            return float(BUCKET_EDGES_MS[index]) if index < len(BUCKET_EDGES_MS) else float(BUCKET_EDGES_MS[-1] * 2)
    return None


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._minutes: dict[int, dict[str, _RouteStats]] = {}
        self.in_flight = 0

    def begin(self) -> None:
        with self._lock:
            self.in_flight += 1

    def end(self, route: str | None, elapsed_ms: float, status: int) -> None:
        minute = int(time.time() // 60)
        with self._lock:
            self.in_flight = max(0, self.in_flight - 1)
            if route is None:
                return
            stats = self._minutes.setdefault(minute, {}).setdefault(route, _RouteStats())
            stats.count += 1
            stats.total_ms += elapsed_ms
            if status >= 500:
                stats.errors += 1
            stats.histogram[bisect_left(BUCKET_EDGES_MS, elapsed_ms)] += 1
            for old in [m for m in self._minutes if m < minute - WINDOW_MINUTES]:
                del self._minutes[old]

    def summary(self, minutes: int = 15, now: float | None = None) -> dict[str, Any]:
        """Aggregate the last `minutes` complete-or-partial minutes."""
        current = int((now if now is not None else time.time()) // 60)
        merged: dict[str, _RouteStats] = {}
        with self._lock:
            for minute, routes in self._minutes.items():
                if minute <= current - minutes:
                    continue
                for route, stats in routes.items():
                    target = merged.setdefault(route, _RouteStats())
                    target.count += stats.count
                    target.errors += stats.errors
                    target.total_ms += stats.total_ms
                    for i, n in enumerate(stats.histogram):
                        target.histogram[i] += n
            in_flight = self.in_flight

        overall = _RouteStats()
        for stats in merged.values():
            overall.count += stats.count
            overall.errors += stats.errors
            overall.total_ms += stats.total_ms
            for i, n in enumerate(stats.histogram):
                overall.histogram[i] += n

        routes = [
            {
                "route": route,
                "count": s.count,
                "errors": s.errors,
                "avg_ms": round(s.total_ms / s.count, 1) if s.count else None,
                "p50_ms": percentile_ms(s.histogram, 50),
                "p95_ms": percentile_ms(s.histogram, 95),
            }
            for route, s in merged.items()
        ]
        # Slowest first, but ignore routes hit too few times to mean anything.
        routes.sort(key=lambda r: (r["count"] >= 3, r["p95_ms"] or 0), reverse=True)
        return {
            "window_minutes": minutes,
            "requests": overall.count,
            "errors": overall.errors,
            "p50_ms": percentile_ms(overall.histogram, 50),
            "p95_ms": percentile_ms(overall.histogram, 95),
            "in_flight": in_flight,
            "slowest_routes": routes[:8],
        }

    def last_minute(self) -> dict[str, Any]:
        s = self.summary(minutes=1)
        return {k: s[k] for k in ("requests", "errors", "p95_ms", "in_flight")}


request_metrics = RequestMetrics()


class RequestMetricsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        started = time.perf_counter()
        status = 500
        request_metrics.begin()

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            try:
                route = getattr(scope.get("route"), "path", None) or "unmatched"
                skipped = scope["method"] == "OPTIONS" or scope["path"].startswith(EXCLUDED_PREFIXES)  # preflights aren't real work
                recorded = None if skipped else f"{scope['method']} {route}"
                request_metrics.end(recorded, (time.perf_counter() - started) * 1000, status)
            except Exception:  # monitoring must never break a request
                pass
