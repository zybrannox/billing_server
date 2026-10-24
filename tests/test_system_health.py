import os
import time

import pytest
from passlib.hash import bcrypt

from app.entities import SystemMetric, User, UserRole
from app.security import create_access_token
from app.system_health import collector, history
from app.system_health.diagnosis import diagnose
from app.system_health.metrics import RequestMetrics, percentile_ms

HEALTHY_MACHINE = {
    "memory_available_pct": 40, "swap_used_mb": 0, "load_per_core": 0.2,
    "disk_free_pct": 50, "disk_free_gb": 200,
}
NO_PROCESSES = {"components": [], "other_top": []}
QUIET = {"requests": 0, "errors": 0, "p95_ms": None}


def _diagnose(machine=None, processes=None, pool=None, performance=None, slow=None, uploads=0):
    return diagnose({**HEALTHY_MACHINE, **(machine or {})}, processes or NO_PROCESSES, pool,
                    {**QUIET, **(performance or {})}, slow or [], uploads)


# ---- access -----------------------------------------------------------------

def _user(db, name, role):
    user = User(username=name, email=f"{name}@example.com", phone="9876543210" if name == "boss" else "9876543211",
                hashed_password=bcrypt.hash("x" * 12), role=role, is_active=True)
    db.add(user)
    db.commit()
    return user


def test_health_endpoints_are_admin_only(client, db):
    assert client.get("/system-health").status_code == 401
    staff = _user(db, "alan", UserRole.USER)
    client.cookies.set("access_token", create_access_token({"sub": staff.username, "role": "user", "tv": 0}))
    assert client.get("/system-health").status_code == 403
    assert client.get("/system-health/history").status_code == 403


def test_admin_gets_a_complete_report_without_leaking_paths_or_command_lines(client, db):
    admin = _user(db, "boss", UserRole.ADMIN)
    client.cookies.set("access_token", create_access_token({"sub": admin.username, "role": "admin", "tv": 0}))
    response = client.get("/system-health")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert {"machine", "processes", "storage", "performance", "diagnosis", "slow_queries"} <= body.keys()
    assert body["machine"]["memory_total_mb"] > 0
    assert body["diagnosis"]["verdict"] in ("ok", "info", "warning", "critical")
    text = response.text
    assert os.getcwd() not in text and "uvicorn" not in text and "SECRET_KEY" not in text


def test_the_health_endpoint_does_not_count_itself_in_latency_stats(client, db):
    from app.system_health.metrics import request_metrics

    admin = _user(db, "boss", UserRole.ADMIN)
    client.cookies.set("access_token", create_access_token({"sub": admin.username, "role": "admin", "tv": 0}))
    before = request_metrics.summary(minutes=1)["requests"]
    client.get("/system-health")
    client.get("/auth/me")
    summary = request_metrics.summary(minutes=1)
    assert summary["requests"] == before + 1
    assert any(r["route"] == "GET /auth/me" for r in summary["slowest_routes"])  # grouped by route template


# ---- metrics ----------------------------------------------------------------

def test_percentiles_come_from_the_histogram():
    metrics = RequestMetrics()
    for ms in [3] * 90 + [900] * 10:
        metrics.end("GET /x", ms, 200)
    summary = metrics.summary(minutes=5)
    assert summary["requests"] == 100
    assert summary["p50_ms"] == 5
    assert summary["p95_ms"] == 1600  # upper edge of the 800-1600 bucket
    assert percentile_ms([0] * 12, 95) is None


def test_errors_are_counted_and_old_minutes_age_out():
    metrics = RequestMetrics()
    metrics.end("GET /x", 10, 500)
    metrics.end("GET /x", 10, 200)
    assert metrics.summary(minutes=5)["errors"] == 1
    assert metrics.summary(minutes=5, now=time.time() + 3600)["requests"] == 0


def test_cors_preflights_are_not_counted(client, db):
    from app.system_health.metrics import request_metrics

    before = request_metrics.summary(minutes=1)["requests"]
    client.options("/auth/me", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert request_metrics.summary(minutes=1)["requests"] == before


def test_memory_stays_bounded_however_many_requests():
    metrics = RequestMetrics()
    for i in range(20000):
        metrics.end("GET /x", i % 700, 200)
    stats = metrics._minutes[next(iter(metrics._minutes))]["GET /x"]
    assert len(stats.histogram) == 12  # fixed size, no per-request samples


# ---- diagnosis --------------------------------------------------------------

def test_healthy_machine_reports_ok():
    result = _diagnose()
    assert result["verdict"] == "ok" and result["findings"][0]["title"] == "Everything looks healthy"


def test_swap_and_low_memory_names_the_biggest_consumer():
    processes = {"components": [{"role": "Database (Postgres)", "memory_mb": 1500, "memory_pct": 18, "processes": 9,
                                 "approximate": True, "memory_known": True}],
                 "other_top": [{"name": "Google Chrome", "memory_mb": 3200, "memory_pct": 40}]}
    result = _diagnose({"memory_available_pct": 4, "swap_used_mb": 3000}, processes)
    assert result["verdict"] == "critical"
    finding = result["findings"][0]
    assert "out of memory" in finding["title"] and "Google Chrome" in finding["detail"]
    assert any("Google Chrome" in f["title"] for f in result["findings"])  # a non-app hog is called out


@pytest.mark.parametrize("machine,expected", [
    ({"load_per_core": 2.5}, "CPU is overloaded"),
    ({"disk_free_pct": 3, "disk_free_gb": 8}, "disk is almost full"),
    ({"disk_free_pct": 8, "disk_free_gb": 20}, "disk is filling up"),
])
def test_cpu_and_disk_rules(machine, expected):
    assert expected in _diagnose(machine)["findings"][0]["title"]


def test_slow_requests_on_a_healthy_machine_point_at_the_database():
    slow = [{"at": None, "ms": 2400, "statement": "SELECT ..."}]
    result = _diagnose(performance={"requests": 50, "p95_ms": 1600, "errors": 0}, slow=slow)
    assert "machine is fine" in result["findings"][0]["title"] and "2400" in result["findings"][0]["detail"]


def test_slow_requests_during_a_resource_problem_blame_the_resource_first():
    result = _diagnose({"memory_available_pct": 3, "swap_used_mb": 4000},
                       performance={"requests": 50, "p95_ms": 3200, "errors": 0})
    assert result["findings"][0]["severity"] == "critical"
    assert any(f["severity"] == "info" and "consistent" in f["detail"] for f in result["findings"])


def test_pool_exhaustion_and_error_rate_are_flagged():
    result = _diagnose(pool={"size": 20, "in_use": 18}, performance={"requests": 100, "errors": 9, "p95_ms": 50})
    titles = " ".join(f["title"] for f in result["findings"])
    assert "database connections" in titles and "failing" in titles


# ---- storage and history ----------------------------------------------------

def test_storage_scan_sizes_folders_and_never_follows_symlinks(tmp_path, monkeypatch):
    (tmp_path / "thumbnails").mkdir()
    (tmp_path / ".chunked").mkdir()
    (tmp_path / "a.pdf").write_bytes(b"x" * 2_000_000)
    (tmp_path / "thumbnails" / "a.pdf").write_bytes(b"x" * 500_000)
    (tmp_path / ".chunked" / "u.part").write_bytes(b"x" * 1_000_000)
    outside = tmp_path.parent / "outside_secret.bin"
    outside.write_bytes(b"x" * 9_000_000)
    (tmp_path / "link").symlink_to(outside)
    monkeypatch.setattr(collector, "_uploads_dir", lambda: tmp_path)
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "no-backups"))

    report = collector.refresh_storage()
    sizes = {f["label"]: f["size_mb"] for f in report.folders}
    assert sizes["Customer files"] == pytest.approx(1.9, abs=0.1)
    assert sizes["Image previews (thumbnails)"] == pytest.approx(0.5, abs=0.1)
    assert sizes["Unfinished uploads"] == pytest.approx(1.0, abs=0.1)
    assert report.complete


def test_storage_scan_gives_up_at_its_time_budget(tmp_path):
    for i in range(50):
        (tmp_path / f"f{i}").write_bytes(b"x")
    total, files, complete = collector._scan(tmp_path, deadline=time.monotonic() - 1)
    assert not complete


def test_history_snapshots_are_stored_purged_and_downsampled(db, monkeypatch):
    history.record_snapshot()
    assert db.query(SystemMetric).count() == 1
    from datetime import timedelta
    from app.datetime_utils import utcnow

    db.add(SystemMetric(at=utcnow() - timedelta(days=9), memory_available_pct=1, swap_used_mb=0, load_per_core=0,
                        disk_free_pct=1, app_memory_mb=0, requests=0, errors=0))
    db.commit()
    history.record_snapshot()
    assert db.query(SystemMetric).filter(SystemMetric.memory_available_pct == 1).count() == 0  # 9-day-old row purged
    for _ in range(300):
        db.add(SystemMetric(memory_available_pct=50, swap_used_mb=0, load_per_core=0, disk_free_pct=50,
                            app_memory_mb=0, requests=0, errors=0))
    db.commit()
    assert len(history.history(db, minutes=60)) <= 120
