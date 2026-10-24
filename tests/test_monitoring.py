import logging

from sqlalchemy import create_engine, text

from app.database import slow_queries
from app.monitoring import _scrub, init_monitoring


def test_sentry_is_off_without_a_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert init_monitoring() is False


def test_error_reports_carry_no_request_data():
    event = {"request": {"url": "http://x/invoices", "data": {"card": "1"}, "cookies": {"access_token": "t"},
                         "headers": {"cookie": "t"}, "query_string": "q=1"}, "exception": {}}
    cleaned = _scrub(event, {})
    assert cleaned["request"] == {"url": "http://x/invoices"}


def test_slow_queries_are_logged_without_parameters(monkeypatch, caplog):
    monkeypatch.setenv("SLOW_QUERY_MS", "0.0001")
    engine = create_engine("sqlite://")
    slow_queries.install(engine)
    with caplog.at_level(logging.WARNING, logger="app.slow_query"):
        with engine.connect() as conn:
            conn.execute(text("SELECT :secret"), {"secret": "hunter2-do-not-log"})
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "slow query" in messages and "SELECT" in messages
    assert "hunter2" not in messages
