"""Turn raw numbers into a plain-English "why might it be slow?" answer.

A pure function of the data it is given, so every rule is unit-tested and the
thresholds are all visible in one place.
"""
from typing import Any

SEVERITY_ORDER = {"ok": 0, "info": 1, "warning": 2, "critical": 3}


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

    # --- memory -------------------------------------------------------------
    available_pct, swap_mb = machine["memory_available_pct"], machine["swap_used_mb"]
    if available_pct < 8 or swap_mb > 2048:
        culprit = f" The biggest user is {biggest[1]} ({biggest[0]:.0f} MB)." if biggest else ""
        findings.append(_finding(
            "critical", "The machine is out of memory",
            f"Only {available_pct:.0f}% of RAM is free and {swap_mb:.0f} MB has spilled to disk (swap), "
            f"which makes everything slow.{culprit}",
            "Close or quit whatever isn't needed on this Mac, then restart the heaviest process. "
            "Lower DB_POOL_SIZE if the database is the heavy one.",
        ))
    elif available_pct < 15 or swap_mb > 512:
        culprit = f" Biggest user: {biggest[1]} ({biggest[0]:.0f} MB)." if biggest else ""
        findings.append(_finding(
            "warning", "Memory is getting tight",
            f"{available_pct:.0f}% of RAM is free, {swap_mb:.0f} MB in swap.{culprit}",
            "Keep an eye on it; free some memory before it starts to lag.",
        ))

    # --- one process hogging RAM -------------------------------------------
    for other in processes.get("other_top", [])[:1]:
        if other["memory_pct"] >= 25:
            findings.append(_finding(
                "warning", f"{other['name']} is using {other['memory_pct']:.0f}% of the RAM",
                "That is not part of this application, so it is competing with it for memory.",
                "Quit it on the server Mac, or move it elsewhere.",
            ))

    # --- CPU ----------------------------------------------------------------
    load = machine["load_per_core"]
    if load >= 2:
        findings.append(_finding(
            "critical", "The CPU is overloaded",
            f"Load is {load:.1f} per core (1.0 means fully busy).",
            "Look for a runaway process in Top processes; large image uploads and thumbnail jobs are heavy.",
        ))
    elif load >= 1:
        findings.append(_finding(
            "warning", "The CPU is busy", f"Load is {load:.1f} per core.",
            "If this keeps up, check what is running in Top processes.",
        ))

    # --- disk ---------------------------------------------------------------
    free = machine["disk_free_pct"]
    if free < 5:
        findings.append(_finding(
            "critical", "The disk is almost full",
            f"Only {free:.0f}% ({machine['disk_free_gb']:.1f} GB) is free. A full disk makes uploads fail and slows the database.",
            "Delete old backups or customer files, or move the uploads folder to a bigger drive.",
        ))
    elif free < 10:
        findings.append(_finding(
            "warning", "The disk is filling up",
            f"{free:.0f}% ({machine['disk_free_gb']:.1f} GB) is free.",
            "Plan to clear space or add storage soon.",
        ))

    # --- database connections ----------------------------------------------
    if pool and pool["size"] and pool["in_use"] / pool["size"] >= 0.8:
        findings.append(_finding(
            "warning", "Nearly all database connections are in use",
            f"{pool['in_use']} of {pool['size']} are busy, so new requests may have to wait.",
            "Usually a symptom of slow queries (see below). Raising DB_POOL_SIZE adds memory use.",
        ))

    # --- app latency / errors ----------------------------------------------
    p95 = performance.get("p95_ms")
    requests = performance.get("requests", 0)
    system_stressed = any(f["severity"] in ("critical", "warning") for f in findings)
    if requests >= 10 and p95 and p95 >= 1000:
        if slow_queries and not system_stressed:
            top = max(slow_queries, key=lambda q: q["ms"])
            findings.append(_finding(
                "warning", "The app is slow but the machine is fine",
                f"Typical slow requests take about {p95 / 1000:.1f}s. The slowest recent database query took "
                f"{top['ms']} ms, so the cause is likely a heavy query.",
                "See Slow database queries below; an index or a smaller page size usually fixes it.",
            ))
        elif not system_stressed:
            findings.append(_finding(
                "warning", "Requests are slow with no obvious machine cause",
                f"About 5% of requests take over {p95 / 1000:.1f}s.",
                "Check Slowest requests below to see which page it is.",
            ))
        else:
            findings.append(_finding(
                "info", "Requests are slow",
                f"About 5% of requests take over {p95 / 1000:.1f}s - consistent with the resource problem above.",
                "Fix that first, then re-check.",
            ))
    if requests >= 20 and performance.get("errors", 0) / requests >= 0.05:
        findings.append(_finding(
            "warning", "Many requests are failing",
            f"{performance['errors']} of the last {requests} requests returned a server error.",
            "Check the backend log (and Sentry, if enabled) for the error.",
        ))

    if active_uploads and (available_pct < 20 or load >= 1):
        findings.append(_finding(
            "info", f"{active_uploads} large upload(s) in progress",
            "Uploads and the thumbnails made from them use a lot of memory and CPU.",
            "It should ease off once they finish.",
        ))

    findings.sort(key=lambda f: SEVERITY_ORDER[f["severity"]], reverse=True)
    verdict = findings[0]["severity"] if findings else "ok"
    if not findings:
        findings.append(_finding(
            "ok", "Everything looks healthy",
            "Memory, CPU, disk, database connections and response times are all within normal range.",
            "Nothing to do.",
        ))
    return {"verdict": verdict, "findings": findings}
