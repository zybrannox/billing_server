import os
from dotenv import load_dotenv

load_dotenv()

# A hardcoded/placeholder value here would let anyone who reads the source
# forge a valid JWT for any user (including admin) - this must come from
# the environment, with no fallback, so a missing secret fails loudly at
# startup instead of silently running with a guessable key.
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours - covers a full work shift

# A second, independent secret for the client portal (see app/client_auth) -
# never falls back to SECRET_KEY. Staff and client tokens must be mutually
# undecodable: a token signed for one system should be structurally
# incapable of passing as the other, not just conventionally treated as
# invalid by a role check that a future bug could get wrong.
CLIENT_SECRET_KEY = os.getenv("CLIENT_SECRET_KEY")
if not CLIENT_SECRET_KEY:
    raise RuntimeError("CLIENT_SECRET_KEY is not set")
# 7 days, not 8 hours - a client isn't at a desk logging in every shift like
# staff.
CLIENT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("CLIENT_ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
IS_PRODUCTION = ENVIRONMENT.lower() == "production"

# Gmail SMTP sender for the forgot-password verification-code emails (see
# app/email_service.py) - not required at import time like SECRET_KEY,
# since the rest of the app works fine with no email configured; the
# forgot-password endpoints themselves check for this and fail with a
# clear error rather than crashing the whole app at startup.
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
# What recipients see as the sender - defaults to GMAIL_ADDRESS itself, but
# can be a "+" alias of it instead (e.g. zybrannox+noreply@gmail.com), which
# Gmail treats as the same mailbox for auth purposes: SMTP still
# authenticates with GMAIL_ADDRESS/GMAIL_APP_PASSWORD, this only changes the
# visible From header, so a dedicated-looking sender doesn't need a second
# Google account or a second app password.
GMAIL_FROM_ADDRESS = os.getenv("GMAIL_FROM_ADDRESS") or GMAIL_ADDRESS
