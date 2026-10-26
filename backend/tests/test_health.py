def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert "version" in body


def test_security_headers_present(client):
    r = client.get("/api/v1/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "Referrer-Policy" in r.headers
    # HSTS só em produção
    assert "Strict-Transport-Security" not in r.headers


def test_docs_available_outside_production(client):
    assert client.get("/api/docs").status_code == 200


def test_body_too_large_is_rejected(client, admin_headers):
    big = "x" * 1_100_000
    r = client.patch("/api/v1/users/me", json={"nome": big}, headers=admin_headers)
    assert r.status_code == 413
