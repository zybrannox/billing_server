"""CSRF header guard, security headers and CORS lists."""


def test_cookie_authenticated_write_without_csrf_header_is_rejected(client):
    r = client.post("/projects/", json={}, headers={"Cookie": "access_token=whatever"})
    assert r.status_code == 403
    assert "header" in r.json()["detail"].lower()


def test_client_portal_cookie_is_also_guarded(client):
    r = client.patch("/client-auth/anything", json={}, headers={"Cookie": "client_access_token=x"})
    assert r.status_code == 403


def test_write_with_csrf_header_reaches_the_app(client):
    r = client.post(
        "/projects/",
        json={},
        headers={"Cookie": "access_token=bad", "X-Requested-With": "XMLHttpRequest"},
    )
    # Past the CSRF layer: now it's the normal auth check that answers.
    assert r.status_code in (401, 422)


def test_cookieless_write_is_not_blocked(client):
    # Login & forgot-password carry no auth cookie, so there's nothing to forge.
    r = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 200


def test_reads_never_need_the_header(client):
    r = client.get("/document-settings/", headers={"Cookie": "access_token=bad"})
    assert r.status_code == 401  # auth, not CSRF


def test_security_headers_on_json_responses(client):
    r = client.get("/document-settings/")
    h = r.headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in h["content-security-policy"]


def test_security_headers_also_on_error_responses(client):
    r = client.post("/projects/", json={}, headers={"Cookie": "access_token=x"})
    assert r.status_code == 403
    assert r.headers["x-content-type-options"] == "nosniff"


def test_auth_responses_are_not_cacheable(client):
    r = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.headers["cache-control"] == "no-store"


def test_cors_preflight_allows_only_listed_methods_and_headers(client):
    r = client.options(
        "/projects/",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-requested-with,content-type",
        },
    )
    assert r.status_code == 200
    assert "x-requested-with" in r.headers["access-control-allow-headers"].lower()
    assert "*" not in r.headers["access-control-allow-headers"]


def test_cors_rejects_unknown_origins(client):
    r = client.options(
        "/projects/",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in r.headers
