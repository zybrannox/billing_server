"""Test harness. The app reads its configuration at import time, so the
environment is pinned *before* anything from `app` is imported:

- an isolated SQLite file instead of the real database (a test must never
  be able to touch dev or production data),
- throw-away signing keys,
- blank Gmail credentials, so no test can ever send a real email even though
  the project's .env (loaded by python-dotenv for anything not already set)
  holds real ones.
"""
import os
import tempfile

_db_file = tempfile.NamedTemporaryFile(prefix="zyb-test-", suffix=".db", delete=False)
_db_file.close()

os.environ["DATABASE_URL"] = f"sqlite:///{_db_file.name}"
os.environ["SECRET_KEY"] = "test-staff-key-" + "s" * 40
os.environ["CLIENT_SECRET_KEY"] = "test-client-key-" + "c" * 40
os.environ["ENVIRONMENT"] = "test"
os.environ["GMAIL_ADDRESS"] = ""
os.environ["GMAIL_APP_PASSWORD"] = ""
os.environ["GMAIL_FROM_ADDRESS"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.entities  # noqa: E402,F401  (registers every table)
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

assert str(engine.url).startswith("sqlite"), "tests must run against the throw-away SQLite database"

# Two tables carry Postgres-only regex CHECK constraints (phone formats, using
# the `~` operator) that SQLite can't parse. Dropped from this process's
# in-memory table definitions only - production schema and migrations are
# untouched, and the format rules are still enforced by the API's own
# validation, which is what the tests exercise.
from sqlalchemy import CheckConstraint  # noqa: E402

for _table in Base.metadata.tables.values():
    for _constraint in list(_table.constraints):
        if isinstance(_constraint, CheckConstraint) and "~" in str(_constraint.sqltext):
            _table.constraints.discard(_constraint)


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # Rate-limit counters are in-memory and process-wide - clear them so one
    # test's requests can never trip another's limit.
    from app.rate_limiting import limiter

    limiter.reset()
    from app import ttl_cache

    ttl_cache.clear()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    # No `with`: skips the app's startup hooks (admin seeding, schedulers).
    return TestClient(app)


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    try:
        os.unlink(_db_file.name)
    except OSError:
        pass
