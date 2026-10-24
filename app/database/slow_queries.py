"""Log any SQL statement slower than SLOW_QUERY_MS (default 300; 0 disables).

Lets a slow list page be traced to its query from the normal server log,
without turning on full statement echo.
"""
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

logger = logging.getLogger("app.slow_query")

# The most recent slow statements, kept in memory (bounded) so the admin
# System Health screen can show what was slow without anyone reading logs.
# Statement text only - never bound parameters.
RECENT_SLOW_QUERIES: deque[dict[str, Any]] = deque(maxlen=20)


def install(engine: Engine) -> None:
    threshold_ms = float(os.getenv("SLOW_QUERY_MS", "300"))
    if threshold_ms <= 0:
        return

    @event.listens_for(engine, "before_cursor_execute")
    def _start(conn, cursor, statement, parameters, context, executemany):
        context._slow_query_start = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _stop(conn, cursor, statement, parameters, context, executemany):
        elapsed_ms = (time.perf_counter() - context._slow_query_start) * 1000
        if elapsed_ms >= threshold_ms:
            # The statement only (never the bound parameters - they can hold
            # personal data or secrets).
            text = " ".join(statement.split())
            logger.warning("slow query %.0f ms: %s", elapsed_ms, text[:500])
            RECENT_SLOW_QUERIES.append(
                {"at": datetime.now(timezone.utc), "ms": round(elapsed_ms), "statement": text[:240]}
            )
