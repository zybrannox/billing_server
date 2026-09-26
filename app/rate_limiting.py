from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared across every rate-limited route (see app/main.py's registration and
# the @limiter.limit(...) decorators on /auth/login and /client-auth/login) -
# one Limiter instance, one IP-based counter, not a per-router copy.
# Previously this file stood up its own separate, never-imported FastAPI()
# app with a fake /login stub - it looked like login was rate-limited but
# the real /auth/login and /client-auth/login had no throttling at all,
# leaving both open to unlimited brute-force password guessing.
limiter = Limiter(key_func=get_remote_address)
