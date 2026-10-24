from datetime import timedelta

import pytest
from fastapi import HTTPException
from passlib.hash import bcrypt

from app import account_lockout
from app.auth.service import AuthService
from app.datetime_utils import utcnow
from app.entities import AuditLog, User, UserRole
from app.entities.project import Project
from app.invoices.model import InvoiceCreate, InvoiceItemCreate
from app.invoices.repository import create_invoice
from app.security import create_access_token


def _user(db, username="alan", role=UserRole.USER):
    user = User(
        username=username,
        email=f"{username}@example.com",
        phone="9876543210" if username == "alan" else "9876543211",
        hashed_password=bcrypt.hash("correct horse battery"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def _login(db, password):
    return AuthService.authenticate_user(db, "alan@example.com", password)


# ---- lockout ---------------------------------------------------------------

def test_account_locks_after_repeated_failures_and_refuses_even_the_right_password(db, monkeypatch):
    monkeypatch.setattr(account_lockout, "LOGIN_MAX_FAILURES", 3)
    _user(db)
    for _ in range(3):
        with pytest.raises(HTTPException) as err:
            _login(db, "wrong")
        assert err.value.status_code == 401

    with pytest.raises(HTTPException) as err:
        _login(db, "correct horse battery")
    assert err.value.status_code == 429 and "Try again" in err.value.detail

    # the lock is recorded for later review
    assert db.query(AuditLog).filter_by(action="auth.lockout").count() == 1


def test_lock_expires_by_itself_and_a_good_login_clears_the_count(db, monkeypatch):
    monkeypatch.setattr(account_lockout, "LOGIN_MAX_FAILURES", 2)
    user = _user(db)
    for _ in range(2):
        with pytest.raises(HTTPException):
            _login(db, "wrong")
    db.refresh(user)
    user.locked_until = utcnow() - timedelta(seconds=1)  # lock has run out
    db.commit()

    assert _login(db, "correct horse battery")  # token issued
    db.refresh(user)
    assert user.failed_login_count == 0 and user.locked_until is None


def test_a_good_login_in_between_resets_the_failure_streak(db, monkeypatch):
    monkeypatch.setattr(account_lockout, "LOGIN_MAX_FAILURES", 3)
    _user(db)
    for _ in range(2):
        with pytest.raises(HTTPException):
            _login(db, "wrong")
    assert _login(db, "correct horse battery")
    for _ in range(2):  # would be the 3rd/4th failure without the reset
        with pytest.raises(HTTPException) as err:
            _login(db, "wrong")
        assert err.value.status_code == 401


# ---- audit log -------------------------------------------------------------

@pytest.fixture
def admin_headers(db):
    admin = _user(db, "boss", UserRole.ADMIN)
    token = create_access_token({"sub": admin.username, "role": "admin"})
    return {"X-Requested-With": "test"}, {"access_token": token}


@pytest.fixture
def invoice(db):
    project = Project(
        project_type="Flex", assigned_to="alan", priority="Normal", client_status="Confirmed",
        start_date=utcnow(), delivery_date=utcnow(),
    )
    db.add(project)
    db.commit()
    items = [InvoiceItemCreate(description="Banner", width=10, height=10, rate=10, pieces=1, unit="ft")]
    return create_invoice(db, InvoiceCreate(project_id=project.id, items=items), "tester")


def test_payments_cancellations_and_deletes_are_audited(client, admin_headers, invoice):
    headers, cookies = admin_headers
    client.cookies.update(cookies)

    assert client.patch(
        f"/invoices/{invoice.id}/record-payment", headers=headers,
        json={"amount": 250, "payment_method": "Cash"},
    ).status_code == 200
    assert client.patch(f"/invoices/{invoice.id}", headers=headers, json={"status": "cancelled"}).status_code == 200
    assert client.delete(f"/invoices/{invoice.id}", headers=headers).status_code == 200

    rows = client.get("/audit-log/", headers=headers).json()["items"]
    assert [r["action"] for r in rows] == ["invoice.delete", "invoice.cancel", "invoice.payment"]
    assert all(r["actor"] == "boss" and r["entity_id"] == invoice.id for r in rows)
    assert rows[2]["detail"]["amount"] == 250
    assert rows[0]["detail"]["label"] == invoice.invoice_number  # still says what was deleted


def test_audit_log_is_admin_only_and_filterable(client, db, admin_headers):
    headers, cookies = admin_headers
    user = _user(db)
    token = create_access_token({"sub": user.username, "role": "user"})
    assert client.get("/audit-log/", headers=headers, cookies={"access_token": token}).status_code == 403

    client.cookies.update(cookies)
    assert client.get("/audit-log/?action=invoice.delete", headers=headers).json()["total"] == 0


# ---- session revocation ----------------------------------------------------

def _token(user):
    return create_access_token({"sub": user.username, "role": user.role.value, "tv": user.token_version})


def test_revoking_sessions_invalidates_tokens_already_issued(client, db):
    admin = _user(db, "boss", UserRole.ADMIN)
    staff = _user(db)
    old = _token(staff)
    client.cookies.set("access_token", old)
    assert client.get("/auth/me").status_code == 200

    client.cookies.set("access_token", _token(admin))
    r = client.post(f"/users/{staff.id}/revoke-sessions", headers={"X-Requested-With": "test"})
    assert r.status_code == 200

    client.cookies.set("access_token", old)
    assert client.get("/auth/me").status_code == 401  # signed out everywhere
    db.refresh(staff)
    client.cookies.set("access_token", _token(staff))
    assert client.get("/auth/me").status_code == 200  # a fresh login works


def test_tokens_issued_before_the_claim_existed_keep_working(client, db):
    staff = _user(db)
    legacy = create_access_token({"sub": staff.username, "role": "user"})  # no "tv"
    client.cookies.set("access_token", legacy)
    assert client.get("/auth/me").status_code == 200


def test_password_reset_signs_out_existing_sessions_and_clears_lockout(client, db):
    staff = _user(db)
    old = _token(staff)
    staff.reset_code, staff.reset_code_expires_at = "123456", utcnow() + timedelta(minutes=10)
    staff.locked_until, staff.failed_login_count = utcnow() + timedelta(minutes=5), 4
    db.commit()
    r = client.post("/auth/reset-password", json={"email": staff.email, "code": "123456",
                                                   "new_password": "a brand new passphrase"})
    assert r.status_code == 200
    client.cookies.set("access_token", old)
    assert client.get("/auth/me").status_code == 401
    db.refresh(staff)
    assert staff.locked_until is None and staff.failed_login_count == 0
