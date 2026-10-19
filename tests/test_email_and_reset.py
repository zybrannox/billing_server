import smtplib
import ssl
from datetime import datetime, timedelta

import pytest
from passlib.hash import bcrypt
from pydantic import SecretStr

import app.auth.controller as auth_controller
import app.email_service as email_service
from app.entities import User, UserRole


class FakeSMTP:
    instances: list = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.tls_context = None
        self.logged_in_as = None
        self.sent = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.tls_context = context

    def login(self, user, password):
        self.logged_in_as = (user, password)

    def sendmail(self, sender, recipient, message):
        self.sent.append((sender, recipient, message))


@pytest.fixture
def configured_mail(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_service, "GMAIL_ADDRESS", "sender@example.com")
    monkeypatch.setattr(email_service, "GMAIL_FROM_ADDRESS", "sender+noreply@example.com")
    monkeypatch.setattr(email_service, "GMAIL_APP_PASSWORD", SecretStr("app-password-value"))
    return FakeSMTP


def test_smtp_uses_a_verifying_tls_context_and_a_timeout(configured_mail):
    email_service.send_email("user@example.com", "Hi", "Body")
    smtp = configured_mail.instances[0]
    assert isinstance(smtp.tls_context, ssl.SSLContext)
    assert smtp.tls_context.verify_mode == ssl.CERT_REQUIRED
    assert smtp.tls_context.check_hostname is True
    assert smtp.timeout and smtp.timeout <= 30
    assert smtp.logged_in_as == ("sender@example.com", "app-password-value")


def test_check_credentials_logs_in_without_sending(configured_mail):
    email_service.check_credentials()
    smtp = configured_mail.instances[0]
    assert smtp.logged_in_as is not None and smtp.sent == []


def test_check_credentials_fails_clearly_when_unconfigured(monkeypatch):
    monkeypatch.setattr(email_service, "GMAIL_APP_PASSWORD", None)
    with pytest.raises(RuntimeError):
        email_service.check_credentials()


def test_background_send_failure_is_logged_not_raised_and_never_leaks_secrets(configured_mail, monkeypatch, caplog):
    def boom(*a, **k):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(configured_mail, "login", boom)
    with caplog.at_level("ERROR"):
        email_service.send_password_reset_code("user@example.com", "123456")  # must not raise
    log_text = " ".join(r.getMessage() for r in caplog.records)
    assert "123456" not in log_text and "app-password-value" not in log_text


@pytest.fixture
def staff_user(db):
    user = User(
        username="alan",
        email="alan@example.com",
        phone="9876543210",
        hashed_password=bcrypt.hash("an-existing-password"),
        role=UserRole.USER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def sent_codes(monkeypatch):
    sent = []
    monkeypatch.setattr(auth_controller, "send_password_reset_code", lambda email, code: sent.append((email, code)))
    return sent


def test_forgot_password_answers_identically_for_known_and_unknown_emails(client, staff_user, sent_codes):
    known = client.post("/auth/forgot-password", json={"email": "alan@example.com"})
    unknown = client.post("/auth/forgot-password", json={"email": "ghost@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    # Only the real account gets mail, and it's sent after the response.
    assert [e for e, _ in sent_codes] == ["alan@example.com"]


def test_reset_code_is_single_use_and_checked_in_constant_time(client, db, staff_user):
    staff_user.reset_code = "654321"
    staff_user.reset_code_expires_at = datetime.utcnow() + timedelta(minutes=10)
    db.commit()
    good = {"email": "alan@example.com", "code": "654321", "new_password": "a brand new passphrase"}

    assert client.post("/auth/reset-password", json={**good, "code": "000000"}).status_code == 400
    assert client.post("/auth/reset-password", json=good).status_code == 200
    assert client.post("/auth/reset-password", json=good).status_code == 400  # replay refused


def test_reset_rejects_a_weak_new_password(client, db, staff_user):
    staff_user.reset_code = "111222"
    staff_user.reset_code_expires_at = datetime.utcnow() + timedelta(minutes=10)
    db.commit()
    r = client.post(
        "/auth/reset-password",
        json={"email": "alan@example.com", "code": "111222", "new_password": "password123"},
    )
    assert r.status_code == 422
