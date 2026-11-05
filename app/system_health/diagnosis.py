"""Turn raw numbers into a plain-English "why might it be slow?" answer.

A pure function of the data it is given, so every rule is unit-tested and the
thresholds are all visible in one place.
"""
from typing import Any

SEVERITY_ORDER = {"ok": 0, "info": 1, "warning": 2, "critical": 3}


def _size(mb: float) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


def _finding(severity: str, title: str, detail: str, action: str) -> dict[str, str]:
    return {"severity": severity, "title": title, "detail": detail, "action": action}


def diagnose(
    machine: dict[str, Any],
    processes: dict[str, Any],
    pool: dict[str, int] | None,
    performance: dict[str, Any],
    slow_queries: list[dict[str, Any]],
    active_uploads: int,
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []

    biggest = None
    candidates = [(c["memory_mb"], c["role"]) for c in processes.get("components", []) if c.get("memory_known", True)] + [
        (o["memory_mb"], o["name"]) for o in processes.get("other_top", [])
    ]
    if candidates:
        biggest = max(candidates)

    # Written for whoever runs the shop, not for a developer: what is happening,
    # why it matters, and what to do about it.

    # --- memory -------------------------------------------------------------
    available_pct, swap_mb = machine["memory_available_pct"], machine["swap_used_mb"]
    if available_pct < 8 or swap_mb > 2048:
        culprit = f" {biggest[1]} is using the most ({_size(biggest[0])})." if biggest else ""
        findings.append(_finding(
            "critical", "The server has run out of memory",
            f"Only {available_pct:.0f}% of its memory is free, so everything in the app will feel slow.{culprit}",
            "Close any programs you aren't using on the server computer. If it's still slow, restart that computer.",
        ))
    elif available_pct < 15 or swap_mb > 512:
        culprit = f" {biggest[1]} is using the most ({_size(biggest[0])})." if biggest else ""
        findings.append(_finding(
            "warning", "The server is running low on memory",
            f"Only {available_pct:.0f}% of its memory is free. The app may start to feel slow.{culprit}",
            "Close any programs you aren't using on the server computer.",
        ))

    # --- one process hogging RAM -------------------------------------------
    for other in processes.get("other_top", [])[:1]:
        if other["memory_pct"] >= 25:
            findings.append(_finding(
                "warning", f"{other['name']} is using {other['memory_pct']:.0f}% of the server's memory",
                "It isn't part of this app, so it leaves less memory for the app.",
                "If nobody needs it, close it on the server computer.",
            ))

    # --- CPU ----------------------------------------------------------------
    load = machine["load_per_core"]
    if load >= 2:
        findings.append(_finding(
            "critical", "The server is overloaded",
            "It has more work than it can keep up with, so the app will feel slow. "
            "Large uploads and big downloads are the usual cause.",
            "Wait for large uploads or downloads to finish. If it stays like this, restart the server computer.",
        ))
    elif load >= 1:
        findings.append(_finding(
            "warning", "The server is very busy",
            "It's working at full capacity, so the app may feel a little slow.",
            "Usually this passes by itself. If it lasts more than an hour, restart the server computer.",
        ))

    # --- disk ---------------------------------------------------------------
    free = machine["disk_free_pct"]
    if free < 5:
        findings.append(_finding(
            "critical", "The disk is almost full",
            f"Only {machine['disk_free_gb']:.1f} GB is left. When it's full, uploads will fail and the app can stop working.",
            "Free up space now: empty the Bin in System setup, delete old backups, or move files to a bigger drive.",
        ))
    elif free < 10:
        findings.append(_finding(
            "warning", "The disk is filling up",
            f"{machine['disk_free_gb']:.1f} GB is left. When it's full, uploads will fail.",
            "Free up some space soon: empty the Bin in System setup or delete old backups.",
        ))

    # --- database connections ----------------------------------------------
    if pool and pool["size"] and pool["in_use"] / pool["size"] >= 0.8:
        findings.append(_finding(
            "warning", "The app is handling a lot of requests at once",
            "New requests may have to wait a moment before they're answered.",
            "This usually clears by itself. If it keeps happening, tell your developer.",
        ))

    # --- app latency / errors ----------------------------------------------
    p95 = performance.get("p95_ms")
    requests = performance.get("requests", 0)
    system_stressed = any(f["severity"] in ("critical", "warning") for f in findings)
    if requests >= 10 and p95 and p95 >= 1000:
        if slow_queries and not system_stressed:
            top = max(slow_queries, key=lambda q: q["ms"])
            findings.append(_finding(
                "warning", "Some pages are slow, but the server is fine",
                f"The slowest pages take about {p95 / 1000:.1f} seconds to open. "
                f"Looking up the data took up to {top['ms'] / 1000:.1f} seconds, so that's the likely cause.",
                "Nothing you can fix from here. If it bothers you, tell your developer.",
            ))
        elif not system_stressed:
            findings.append(_finding(
                "warning", "Some pages are slow",
                f"The slowest pages take about {p95 / 1000:.1f} seconds to open, and the server itself looks fine.",
                "Nothing you can fix from here. If it bothers you, tell your developer.",
            ))
        else:
            findings.append(_finding(
                "info", "Some pages are slow",
                f"The slowest pages take about {p95 / 1000:.1f} seconds to open, because of the problem above.",
                "Fix that first, and this should improve by itself.",
            ))
    if requests >= 20 and performance.get("errors", 0) / requests >= 0.05:
        findings.append(_finding(
            "warning", "Some actions are failing",
            f"{performance['errors']} of the last {requests} requests ended in an error, so people may be seeing error messages.",
            "Tell your developer. They can find the cause in the server's log.",
        ))

    if active_uploads and (available_pct < 20 or load >= 1):
        findings.append(_finding(
            "info", f"{active_uploads} large upload{'s' if active_uploads != 1 else ''} in progress",
            "Large uploads use a lot of the server's capacity while they run.",
            "It should ease off once they finish.",
        ))

    findings.sort(key=lambda f: SEVERITY_ORDER[f["severity"]], reverse=True)
    verdict = findings[0]["severity"] if findings else "ok"
    if not findings:
        findings.append(_finding(
            "ok", "Everything looks healthy",
            "The app is responding quickly and the server has plenty of room.",
            "Nothing to do.",
        ))
    return {"verdict": verdict, "findings": findings}
