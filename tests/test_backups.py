"""Backups: admins only, and the page tells the truth about what's there."""
import os
import subprocess
import time

import pytest
from passlib.hash import bcrypt

from app.backups import service
from app.entities import AuditLog, User, UserRole
from app.security import create_access_token


def _sign_in(client, db, name, role=UserRole.USER, permissions=None):
    user = User(username=name, email=f"{name}@example.com", phone=str(9000000000 + abs(hash(name)) % 999999999)[:10],
                hashed_password=bcrypt.hash("x" * 12), role=role, is_active=True, permissions=permissions or [])
    db.add(user)
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": name, "role": role.value, "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"
    return user


def _dump(folder, name, age_hours=0, size=10):
    path = folder / name
    path.write_bytes(b"x" * size)
    moment = time.time() - age_hours * 3600
    os.utime(path, (moment, moment))
    return path


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(service, "_is_scheduled", lambda: True)
    return tmp_path


@pytest.fixture
def admin(client, db):
    return _sign_in(client, db, "boss", UserRole.ADMIN)


def _succeed(monkeypatch, folder):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        _dump(folder, "billing-new.dump")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(service.subprocess, "run", run)
    return calls


def test_backups_need_a_login(client):
    assert client.get("/backups").status_code == 401


@pytest.mark.parametrize("method,path", [("get", "/backups"), ("post", "/backups/run")])
def test_an_employee_is_refused_whatever_else_they_can_do(client, db, folder, monkeypatch, method, path):
    calls = _succeed(monkeypatch, folder)
    _sign_in(client, db, "ravi", permissions=["invoice.create", "invoice.edit", "workspace.manage", "notes.access"])
    assert getattr(client, method)(path).status_code == 403
    assert calls == []


def test_an_admin_sees_the_status(client, folder, admin):
    assert client.get("/backups").status_code == 200


def test_no_backups_yet_is_overdue(client, folder, admin):
    body = client.get("/backups").json()
    assert (body["backup_count"], body["last_backup_at"], body["overdue"]) == (0, None, True)


def test_a_missing_backup_folder_is_not_an_error(client, folder, admin, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(folder / "nope"))
    body = client.get("/backups").json()
    assert (body["backup_count"], body["on_separate_disk"]) == (0, False)


def test_the_status_reads_the_newest_dump_and_ignores_other_files(client, folder, admin):
    _dump(folder, "billing-old.dump", age_hours=30, size=100)
    _dump(folder, "billing-new.dump", age_hours=1, size=25)
    _dump(folder, "notes.txt", size=999)
    body = client.get("/backups").json()
    assert (body["backup_count"], body["last_backup_size_bytes"], body["total_size_bytes"]) == (2, 25, 125)
    assert body["overdue"] is False


def test_a_backup_older_than_a_day_is_overdue(client, folder, admin):
    _dump(folder, "billing-old.dump", age_hours=30)
    assert client.get("/backups").json()["overdue"] is True


def test_the_status_never_mentions_where_backups_live(client, folder, admin):
    _dump(folder, "billing-new.dump")
    assert str(folder) not in client.get("/backups").text


@pytest.mark.parametrize("written,matched", [("match\n", True), ("differs\n", False)])
def test_the_last_restore_check_is_reported(client, folder, admin, written, matched):
    (folder / ".last_restore_check").write_text(written)
    body = client.get("/backups").json()
    assert body["last_restore_check_matched"] is matched
    assert body["last_restore_check_at"] is not None


def test_a_restore_check_that_never_ran_is_unknown(client, folder, admin):
    body = client.get("/backups").json()
    assert (body["last_restore_check_at"], body["last_restore_check_matched"]) == (None, None)


def test_backing_up_runs_the_script_and_is_logged(client, db, folder, admin, monkeypatch):
    calls = _succeed(monkeypatch, folder)
    res = client.post("/backups/run")
    assert res.status_code == 200
    assert res.json()["backup_count"] == 1
    assert calls == [[str(service.SCRIPT)]]
    assert db.query(AuditLog).filter_by(action="backup.run", actor="boss").count() == 1


def test_a_failed_backup_says_so_without_leaking_the_error(client, db, folder, admin, monkeypatch):
    monkeypatch.setattr(
        service.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "postgresql://postgres:hunter2@localhost failed"),
    )
    res = client.post("/backups/run")
    assert res.status_code == 500
    assert "hunter2" not in res.text
    assert db.query(AuditLog).filter_by(action="backup.run").count() == 0


def test_a_backup_that_times_out_says_so(client, folder, admin, monkeypatch):
    def run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(service.subprocess, "run", run)
    assert client.post("/backups/run").status_code == 500
    assert service._running.acquire(blocking=False)
    service._running.release()


def test_only_one_backup_runs_at_a_time(client, folder, admin, monkeypatch):
    calls = _succeed(monkeypatch, folder)
    assert service._running.acquire(blocking=False)
    try:
        assert client.post("/backups/run").status_code == 409
    finally:
        service._running.release()
    assert calls == []


def test_backing_up_is_rate_limited(client, folder, admin, monkeypatch):
    _succeed(monkeypatch, folder)
    codes = [client.post("/backups/run").status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


def test_notes_need_their_own_access(client, db):
    _sign_in(client, db, "ravi", permissions=["invoice.create", "workspace.manage"])
    assert client.get("/notes/").status_code == 403
    assert client.post("/notes/", json={"text": "x"}).status_code == 403
    assert client.patch("/notes/1", json={"is_done": True}).status_code == 403
    assert client.delete("/notes/1").status_code == 403


def test_notes_work_once_access_is_given(client, db):
    _sign_in(client, db, "ravi", permissions=["notes.access"])
    assert client.post("/notes/", json={"text": "Flex"}).status_code == 200
    assert client.get("/notes/").json()["total"] == 1


def test_an_admin_can_grant_notes(client, db):
    employee = _sign_in(client, db, "ravi")
    _sign_in(client, db, "boss", UserRole.ADMIN)
    res = client.put(f"/users/{employee.id}/permissions", json={"permissions": ["notes.access"]})
    assert res.status_code == 200
    assert res.json()["permissions"] == ["notes.access"]


def test_backups_cant_be_granted_to_an_employee(client, db):
    employee = _sign_in(client, db, "ravi")
    _sign_in(client, db, "boss", UserRole.ADMIN)
    res = client.put(f"/users/{employee.id}/permissions", json={"permissions": ["backups.manage"]})
    assert res.status_code == 422
