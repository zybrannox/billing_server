"""Write the API's OpenAPI document to a file (default: openapi.json).

The frontend generates its TypeScript types from this (`pnpm api:types` in
billing), so the request/response types are never hand-copied. Run it after
changing any route or schema, then regenerate the frontend types:

    ./venv/bin/python scripts/export_openapi.py [path]

It never touches a database or sends email: the environment is pinned to a
throw-away SQLite file with blank credentials before the app is imported (the
app reads its configuration at import time).
"""
import json
import os
import sys
import tempfile

with tempfile.NamedTemporaryFile(prefix="zyb-openapi-", suffix=".db", delete=True) as _db:
    os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"
os.environ["SECRET_KEY"] = "openapi-export-" + "s" * 40
os.environ["CLIENT_SECRET_KEY"] = "openapi-export-" + "c" * 40
os.environ["ENVIRONMENT"] = "test"
os.environ["ENABLE_API_DOCS"] = "false"
for _name in ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "GMAIL_FROM_ADDRESS"):
    os.environ[_name] = ""

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
    with open(target, "w") as fh:
        json.dump(app.openapi(), fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
