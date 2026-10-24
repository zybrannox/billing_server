import logging
import os
from dotenv import load_dotenv

from pydantic import SecretStr

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
IS_PRODUCTION = ENVIRONMENT.lower() == "production"


def _secret(name: str) -> str | None:
    """A secret from the environment, or - the container-secrets convention
    (Docker/Kubernetes/systemd credentials) - from the file named by
    `<NAME>_FILE`. Reading a mounted file means the value never has to sit in
    the process environment (where `ps`, crash dumps and child processes can
    see it) or in a `.env` copied around between machines. The file wins if
    both are set; surrounding whitespace/newline is stripped."""
    file_path = os.getenv(f"{name}_FILE")
    if file_path:
        # A secret file other users can read defeats the point of using one.
        # Warn (rather than refuse to boot, which would take the service down
        # over a stray chmod) so it shows up in the logs to be fixed.
        if os.stat(file_path).st_mode & 0o077:
            logging.getLogger(__name__).warning(
                "%s_FILE (%s) is readable by other users - run: chmod 600 %s", name, file_path, file_path
            )
        with open(file_path, encoding="utf-8") as f:
            return f.read().strip() or None
    value = os.getenv(name)
    return value.strip() if value else None


def _require_signing_key(name: str) -> str:
    value = _secret(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    # A short signing key is brute-forceable offline from any one captured
    # token - refuse to boot production with one rather than run weak.
    if IS_PRODUCTION and len(value) < 32:
        raise RuntimeError(f"{name} must be at least 32 characters in production")
    return value


# A hardcoded/placeholder value here would let anyone who reads the source
# forge a valid JWT for any user (including admin) - this must come from
# the environment, with no fallback, so a missing secret fails loudly at
# startup instead of silently running with a guessable key.
SECRET_KEY = _require_signing_key("SECRET_KEY")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours - covers a full work shift

# A second, independent secret for the client portal (see app/client_auth) -
# never falls back to SECRET_KEY. Staff and client tokens must be mutually
# undecodable: a token signed for one system should be structurally
# incapable of passing as the other, not just conventionally treated as
# invalid by a role check that a future bug could get wrong.
CLIENT_SECRET_KEY = _require_signing_key("CLIENT_SECRET_KEY")
if CLIENT_SECRET_KEY == SECRET_KEY:
    raise RuntimeError("CLIENT_SECRET_KEY must differ from SECRET_KEY")
# 7 days, not 8 hours - a client isn't at a desk logging in every shift like
# staff.
CLIENT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("CLIENT_ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

# Gmail SMTP sender for the forgot-password verification-code emails (see
# app/email_service.py) - not required at import time like SECRET_KEY,
# since the rest of the app works fine with no email configured; the
# forgot-password endpoints themselves check for this and fail with a
# clear error rather than crashing the whole app at startup.
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
# A SecretStr, not a plain string: printing, logging or repr()-ing it (a
# traceback, a debug dump) shows "**********", and the real value has to be
# asked for explicitly with .get_secret_value() - which only
# app/email_service.py does, at the moment it logs in to SMTP.
_gmail_password = _secret("GMAIL_APP_PASSWORD")
GMAIL_APP_PASSWORD: SecretStr | None = SecretStr(_gmail_password) if _gmail_password else None
# What recipients see as the sender - defaults to GMAIL_ADDRESS itself, but
# can be a "+" alias of it instead (e.g. zybrannox+noreply@gmail.com), which
# Gmail treats as the same mailbox for auth purposes: SMTP still
# authenticates with GMAIL_ADDRESS/GMAIL_APP_PASSWORD, this only changes the
# visible From header, so a dedicated-looking sender doesn't need a second
# Google account or a second app password.
GMAIL_FROM_ADDRESS = os.getenv("GMAIL_FROM_ADDRESS") or GMAIL_ADDRESS

# --- Web security -----------------------------------------------------------

# SameSite for the auth cookies. The app (workspace.zybrannox.com) and API
# (workspace-api.zybrannox.com) share a registrable domain, i.e. are
# "same-site", so Lax is enough for the cookie to travel on the app's own
# requests - and, unlike None, it is not attached to requests a third-party
# site triggers, which closes the main CSRF route. Set COOKIE_SAMESITE=none
# only if the app and API are ever served from unrelated domains.
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").lower()
if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise RuntimeError("COOKIE_SAMESITE must be lax, strict or none")

# Interactive API docs (/docs, /redoc, /openapi.json) list every endpoint -
# handy in development, free reconnaissance in production.
# Production refuses to start when the database is behind the Alembic head
# (see app/database/schema.py). Emergency bypass only.
SKIP_SCHEMA_CHECK = os.getenv("SKIP_SCHEMA_CHECK", "false").lower() == "true"

ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "false" if IS_PRODUCTION else "true").lower() == "true"

# How long a WhatsApp/shared document link keeps working after it was last
# generated (see app/shared_documents). Re-sharing the document refreshes it.
SHARE_LINK_EXPIRY_DAYS = int(os.getenv("SHARE_LINK_EXPIRY_DAYS", "30"))
