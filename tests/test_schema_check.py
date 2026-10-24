import pytest
from sqlalchemy import create_engine, text

from app.database import schema


def _engine_at(revision):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        if revision:
            conn.execute(text("INSERT INTO alembic_version VALUES (:r)"), {"r": revision})
    return engine


def test_there_is_exactly_one_migration_head():
    assert len(schema.expected_heads()) == 1


def test_current_schema_passes():
    (head,) = schema.expected_heads()
    schema.assert_schema_is_current(_engine_at(head))


def test_old_schema_is_refused_with_instructions():
    with pytest.raises(schema.SchemaOutOfDate, match="alembic upgrade head"):
        schema.assert_schema_is_current(_engine_at("000000000000"))


def test_unmigrated_database_is_refused():
    with pytest.raises(schema.SchemaOutOfDate):
        schema.assert_schema_is_current(_engine_at(None))
