from slowapi import Limiter
from starlette.requests import Request

_LOOPBACK = ("127.0.0.1", "::1")


def client_ip(request: Request) -> str:
    """The caller's real IP, for per-IP rate limits.

    In production every request reaches the app through the local Cloudflare
    tunnel, so the TCP peer is always 127.0.0.1 - keyed on that, the whole
    company would share one login-attempt budget. Cloudflare puts the real
    address in `CF-Connecting-IP`; it is trusted *only* when the immediate
    peer is loopback (i.e. it really came through the local tunnel), so a
    client connecting directly can't forge it.
    """
    peer = request.client.host if request.client else "unknown"
    if peer in _LOOPBACK:
        forwarded = request.headers.get("cf-connecting-ip")
        if forwarded:
            return forwarded.strip()
    return peer


# Shared across every rate-limited route (see app/main.py's registration and
# the @limiter.limit(...) decorators on /auth/login and /client-auth/login) -
# one Limiter instance, one IP-based counter, not a per-router copy.
limiter = Limiter(key_func=client_ip)
