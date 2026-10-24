"""openapi.json is the contract the frontend generates its types from; a
route or schema change without regenerating it would leave the frontend
typed against a stale API."""
import json
from pathlib import Path

from app.main import app

COMMITTED = Path(__file__).resolve().parent.parent / "openapi.json"


def test_committed_openapi_is_current():
    committed = json.loads(COMMITTED.read_text())
    current = json.loads(json.dumps(app.openapi(), sort_keys=True))
    assert committed == current, (
        "openapi.json is stale - run `./venv/bin/python scripts/export_openapi.py` "
        "and then `pnpm api:types` in billing"
    )
