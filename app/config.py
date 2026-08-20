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

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
IS_PRODUCTION = ENVIRONMENT.lower() == "production"
