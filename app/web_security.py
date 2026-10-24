"""HTTP-level protections applied to every response/request: security headers
and a CSRF guard. Plain ASGI middleware (not BaseHTTPMiddleware) so streaming
responses (file downloads) and background tasks aren't affected."""
import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import ttl_cache
from app.config import IS_PRODUCTION

# State-changing requests must carry this header (see the frontend's axios
# clients, which set it on every call). A custom header can't be added by a
# plain cross-site <form> or <img>, and a cross-site fetch/XHR that adds it
# triggers a CORS preflight, which only our allow-listed origins pass - so a
# malicious page can't make a logged-in browser change anything, even if the
# cookie were attached. This is the "custom request header" CSRF defence
# (OWASP), layered on top of the SameSite cookie attribute.
CSRF_HEADER = b"x-requested-with"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_AUTH_COOKIES = (b"access_token=", b"client_access_token=")


class CsrfHeaderMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in _SAFE_METHODS:
            return await self.app(scope, receive, send)

        headers = dict(scope["headers"])
        # Only requests that ride on an auth cookie can be forged this way;
        # cookie-less ones (login, forgot-password, activate) have nothing for
        # an attacker to piggyback on.
        has_auth_cookie = any(c in headers.get(b"cookie", b"") for c in _AUTH_COOKIES)
        if has_auth_cookie and not headers.get(CSRF_HEADER):
            body = json.dumps({"detail": "Missing required request header."}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


_BASE_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
]
_HSTS = (b"strict-transport-security", b"max-age=63072000; includeSubDomains")
_API_CSP = (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope["path"]
        no_store = path.startswith(("/auth", "/client-auth"))

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                extra = [h for h in _BASE_HEADERS if h[0] not in present]
                if IS_PRODUCTION and _HSTS[0] not in present:
                    extra.append(_HSTS)
                content_type = dict(headers).get(b"content-type", b"")
                # A locked-down CSP for JSON responses; PDFs/images served to
                # browsers (shared documents, thumbnails) need to render, and
                # the interactive docs page loads its own scripts.
                if content_type.startswith(b"application/json") and _API_CSP[0] not in present:
                    extra.append(_API_CSP)
                if no_store and b"cache-control" not in present:
                    extra.append((b"cache-control", b"no-store"))
                message["headers"] = headers + extra
            await send(message)

        await self.app(scope, receive, send_with_headers)


class CacheInvalidationMiddleware:
    """Clears the in-process read cache (app/ttl_cache.py) after any
    successful state-changing request, so cached dashboard numbers never lag
    behind what the user just did."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in _SAFE_METHODS:
            return await self.app(scope, receive, send)

        async def send_and_invalidate(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] < 400:
                ttl_cache.clear()
            await send(message)

        await self.app(scope, receive, send_and_invalidate)
