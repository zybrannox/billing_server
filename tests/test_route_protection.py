"""Every route needs a login unless it's on this short list. A new route fails
here until someone either protects it or deliberately lists it as public."""
import re

from app.main import app

# Reachable without logging in, on purpose: signing in, resetting a password,
# accepting an invite, the customer portal's own sign-in, and health checks.
PUBLIC = {
    ("get", "/"),
    ("post", "/auth/login"),
    ("post", "/auth/logout"),
    ("post", "/auth/forgot-password"),
    ("post", "/auth/reset-password"),
    ("get", "/client-auth/invite/{token}"),
    ("post", "/client-auth/activate"),
    ("post", "/client-auth/login"),
    ("post", "/client-auth/logout"),
    ("post", "/client-auth/forgot-password"),
    ("post", "/client-auth/reset-password"),
    ("get", "/public/documents/{token}"),
}


def _operations():
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            yield method, path


def test_every_route_needs_a_login_unless_listed(client):
    client.cookies.clear()
    client.headers["X-Requested-With"] = "XMLHttpRequest"
    open_routes = set()
    for method, path in _operations():
        url = re.sub(r"\{[^}]+\}", "1", path)
        status = client.request(method.upper(), url, json={}).status_code
        if status not in (401, 403):
            open_routes.add((method, path, status))
    assert {(m, p) for m, p, _ in open_routes} == set(PUBLIC)


def test_public_routes_only_reveal_nothing_for_a_bad_token(client):
    assert client.get("/client-auth/invite/not-a-real-token").json()["valid"] is False
    assert client.get("/public/documents/not-a-real-token").status_code == 404
