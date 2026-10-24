"""Schema lifecycle: Alembic migrations are the only thing that changes a
production database.

`Base.metadata.create_all` is a development convenience - it creates missing
tables but never alters existing ones, so on a long-lived database it quietly
hides a missing migration (new tables appear, new columns don't) until a query
fails. In production the app therefore refuses to start unless the database is
at the Alembic head, and the deploy order is: run migrations, then restart.
"""
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


class SchemaOutOfDate(RuntimeError):
    pass


def expected_heads() -> set[str]:
    return set(ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_heads())


def current_revisions(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return set(MigrationContext.configure(conn).get_current_heads())


def assert_schema_is_current(engine: Engine) -> None:
    expected, current = expected_heads(), current_revisions(engine)
    if current != expected:
        raise SchemaOutOfDate(
            f"Database schema is at {sorted(current) or 'no migration'} but this code expects "
            f"{sorted(expected)}. Run `alembic upgrade head` before starting the app "
            "(set SKIP_SCHEMA_CHECK=true to bypass this check in an emergency)."
        )
