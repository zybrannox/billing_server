import importlib

import pytest


def _reload_config(monkeypatch, **env):
    import app.config as config

    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(config)


@pytest.fixture(autouse=True)
def restore_config():
    yield
    import app.config as config

    importlib.reload(config)


def test_production_refuses_short_signing_keys(monkeypatch):
    with pytest.raises(RuntimeError, match="at least 32"):
        _reload_config(monkeypatch, ENVIRONMENT="production", SECRET_KEY="short")


def test_staff_and_client_keys_must_differ(monkeypatch):
    key = "k" * 40
    with pytest.raises(RuntimeError, match="must differ"):
        _reload_config(monkeypatch, SECRET_KEY=key, CLIENT_SECRET_KEY=key)


def test_secrets_can_come_from_a_file(monkeypatch, tmp_path):
    secret_file = tmp_path / "gmail_password"
    secret_file.write_text("  file-based-secret-value\n")
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    config = _reload_config(monkeypatch, GMAIL_APP_PASSWORD_FILE=str(secret_file))
    assert config.GMAIL_APP_PASSWORD.get_secret_value() == "file-based-secret-value"


def test_gmail_password_never_shows_in_repr_or_str(monkeypatch):
    config = _reload_config(monkeypatch, GMAIL_APP_PASSWORD="super-secret-app-password")
    assert "super-secret" not in repr(config.GMAIL_APP_PASSWORD)
    assert "super-secret" not in str(config.GMAIL_APP_PASSWORD)


def test_unknown_samesite_value_is_rejected(monkeypatch):
    with pytest.raises(RuntimeError, match="COOKIE_SAMESITE"):
        _reload_config(monkeypatch, COOKIE_SAMESITE="sometimes")


def test_api_docs_default_off_in_production(monkeypatch):
    monkeypatch.delenv("ENABLE_API_DOCS", raising=False)
    config = _reload_config(monkeypatch, ENVIRONMENT="production", SECRET_KEY="p" * 40, CLIENT_SECRET_KEY="q" * 40)
    assert config.ENABLE_API_DOCS is False


def test_warns_when_a_secret_file_is_readable_by_others(monkeypatch, tmp_path, caplog):
    loose = tmp_path / "loose"
    loose.write_text("value")
    loose.chmod(0o644)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    with caplog.at_level("WARNING"):
        _reload_config(monkeypatch, GMAIL_APP_PASSWORD_FILE=str(loose))
    assert any("chmod 600" in r.getMessage() for r in caplog.records)


def test_no_warning_for_a_locked_down_secret_file(monkeypatch, tmp_path, caplog):
    tight = tmp_path / "tight"
    tight.write_text("value")
    tight.chmod(0o600)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    with caplog.at_level("WARNING"):
        _reload_config(monkeypatch, GMAIL_APP_PASSWORD_FILE=str(tight))
    assert not any("chmod 600" in r.getMessage() for r in caplog.records)
