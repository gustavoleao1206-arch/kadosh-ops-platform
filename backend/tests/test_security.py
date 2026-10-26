"""Perfil de produção, cabeçalhos, CSRF, limites, IP atrás de proxy, corpo chunked, catch-all do painel."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app import __version__
from app.core import deps
from app.core.config import Settings, get_settings
from app.core.limiter import AttemptLimiter, login_throttle
from app.main import app, create_app
from app.services import users as users_service
from tests.conftest import ADMIN_EMAIL, ADMIN_PASS, SAME_ORIGIN, STAFF_EMAIL, STAFF_PASS, login_android, login_web


# ---------- perfil de produção ----------

def test_settings_production_is_closed_by_default():
    s = Settings(ENV="production", COOKIE_SECURE=False, DOCS_ENABLED=True, TRUST_PROXY_HEADERS=None)
    assert s.COOKIE_SECURE is True and s.DOCS_ENABLED is False and s.TRUST_PROXY_HEADERS is True


def test_settings_refuse_render_without_production(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(ValueError):
        Settings(ENV="development")


def test_database_url_driver_is_forced():
    assert Settings(DATABASE_URL="postgres://u:p@h/db").DATABASE_URL == "postgresql+psycopg://u:p@h/db"
    assert Settings(DATABASE_URL="postgresql://u:p@h/db").DATABASE_URL == "postgresql+psycopg://u:p@h/db"


@pytest.fixture
def production(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ENV", "production")
    monkeypatch.setattr(s, "COOKIE_SECURE", True)
    monkeypatch.setattr(s, "DOCS_ENABLED", False)
    yield s


def test_production_profile(production, admin):
    with TestClient(create_app()) as c:
        assert c.get("/api/docs").status_code == 404
        assert c.get("/api/openapi.json").status_code == 404
        r = c.get("/api/v1/health")
        assert r.headers["Strict-Transport-Security"].startswith("max-age=")
        r = c.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": ADMIN_PASS, "client": "web"})
        cookie = r.headers["set-cookie"].lower()
        assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie


def test_seed_refuses_production(production):
    from app import cli
    from app.seed import seed_demo

    with pytest.raises(RuntimeError):
        seed_demo()
    assert cli.main(["seed-demo"]) == 1


# ---------- cabeçalhos ----------

def test_csp_only_outside_api_and_no_store_inside(client, admin_headers):
    r = client.get("/api/v1/auth/me", headers=admin_headers)
    assert "Content-Security-Policy" not in r.headers
    assert r.headers["Cache-Control"] == "no-store"
    r = client.get("/nao-existe")
    assert "Content-Security-Policy" in r.headers


def test_health_reports_db_down(client):
    from sqlalchemy.exc import OperationalError

    class Broken:
        def execute(self, *_):
            raise OperationalError("SELECT 1", {}, Exception("down"))

    app.dependency_overrides[deps.get_db] = lambda: Broken()
    try:
        r = client.get("/api/v1/health")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    assert r.json() == {"status": "degradado", "db": "erro", "version": __version__}


# ---------- CSRF ----------

class TestCsrfOrigins:
    def test_origin_fallback_same_host_allowed(self, client, admin):
        login_web(client, ADMIN_EMAIL, ADMIN_PASS)
        r = client.patch("/api/v1/users/me", json={"nome": "Pelo Origin"}, headers={"Origin": "http://testserver"})
        assert r.status_code == 200

    def test_origin_fallback_other_host_blocked(self, client, admin):
        login_web(client, ADMIN_EMAIL, ADMIN_PASS)
        r = client.patch("/api/v1/users/me", json={"nome": "Mal"}, headers={"Origin": "http://evil.test"})
        assert r.status_code == 403

    def test_explicit_cross_site_beats_matching_origin(self, client, admin):
        login_web(client, ADMIN_EMAIL, ADMIN_PASS)
        r = client.patch(
            "/api/v1/users/me",
            json={"nome": "Mal"},
            headers={"Origin": "http://testserver", "Sec-Fetch-Site": "cross-site"},
        )
        assert r.status_code == 403

    def test_same_site_is_blocked(self, client, admin):
        login_web(client, ADMIN_EMAIL, ADMIN_PASS)
        r = client.patch("/api/v1/users/me", json={"nome": "Sub"}, headers={"Sec-Fetch-Site": "same-site"})
        assert r.status_code == 403

    def test_web_logout_clears_cookie(self, client, admin):
        login_web(client, ADMIN_EMAIL, ADMIN_PASS)
        assert client.post("/api/v1/auth/logout").status_code == 403  # sem metadados de origem
        r = client.post("/api/v1/auth/logout", headers=SAME_ORIGIN)
        assert r.status_code == 200
        assert "max-age=0" in r.headers["set-cookie"].lower()
        assert client.get("/api/v1/auth/me").status_code == 401


# ---------- limites de tentativas ----------

def test_rate_limit_is_per_ip(admin, rate_limit_on, monkeypatch):
    monkeypatch.setattr(login_throttle.per_source, "free_attempts", 100)  # isola o limite por IP dos outros dois
    with TestClient(app, client=("10.0.0.1", 1)) as a, TestClient(app, client=("10.0.0.2", 1)) as b:
        for _ in range(5):
            a.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": "errada-errada", "client": "android"})
        r = a.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": ADMIN_PASS, "client": "android"})
        assert r.status_code == 429 and r.headers.get("Retry-After")
        r = b.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": ADMIN_PASS, "client": "android"})
        assert r.status_code == 200


def test_source_limit_counts_api_failures_and_clears_on_success(client, admin, staff, monkeypatch):
    monkeypatch.setattr(login_throttle.per_source, "free_attempts", 3)
    for _ in range(3):
        client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": "errada-errada", "client": "android"})
    r = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": ADMIN_PASS, "client": "android"})
    assert r.status_code == 429 and "e-mail" in r.json()["detail"] and r.headers.get("Retry-After")
    # é por e-mail: outro usuário no mesmo IP entra
    assert client.post("/api/v1/auth/login", json={"email": STAFF_EMAIL, "senha": STAFF_PASS, "client": "android"}).status_code == 200
    # o bloqueio é curto (1 s após 3 falhas) e o sucesso limpa o contador
    login_throttle.clear_source(ADMIN_EMAIL, "testclient")
    for _ in range(2):
        client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": "errada-errada", "client": "android"})
    assert client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": ADMIN_PASS, "client": "android"}).status_code == 200
    for _ in range(2):
        client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": "errada-errada", "client": "android"})
    assert client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": ADMIN_PASS, "client": "android"}).status_code == 200


def test_attempt_limiter_does_not_grow_with_unknown_keys():
    lim = AttemptLimiter(free_attempts=5, max_block_seconds=900)
    assert lim.blocked_for("ninguem@x.br") == 0
    assert lim.failures("ninguem@x.br") == 0
    assert "ninguem@x.br" not in lim._attempts


def test_progressive_delay_caps_at_max():
    lim = AttemptLimiter(free_attempts=5, max_block_seconds=900)
    for _ in range(30):
        lim.register_failure("a@b.br")
    assert 0 < lim.blocked_for("a@b.br") <= 900


# ---------- IP atrás do proxy ----------

def test_client_ip_uses_last_forwarded_hop_only_when_trusting_proxy(client, admin, db, monkeypatch):
    from sqlalchemy import select

    from app.models import AuthLog

    s = get_settings()
    monkeypatch.setattr(s, "TRUST_PROXY_HEADERS", True)
    client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "senha": ADMIN_PASS, "client": "android"},
        headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.9"},
    )
    assert db.scalar(select(AuthLog.ip)) == "203.0.113.9"  # último salto, nunca o primeiro (forjável)

    monkeypatch.setattr(s, "TRUST_PROXY_HEADERS", False)
    client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "senha": ADMIN_PASS, "client": "android"},
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    ips = db.scalars(select(AuthLog.ip).order_by(AuthLog.id)).all()
    assert ips[-1] == "testclient"


# ---------- corpo grande ----------

def test_chunked_body_over_limit_is_rejected(client):
    def gen():
        for _ in range(20):
            yield b"x" * 65536

    r = client.post("/api/v1/auth/login", content=gen(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


# ---------- catch-all do painel ----------

def test_spa_never_serves_files_outside_dist(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>painel</h1>", encoding="utf-8")
    (dist / "ok.txt").write_text("ok", encoding="utf-8")
    (tmp_path / "segredo.txt").write_text("SEGREDO", encoding="utf-8")
    monkeypatch.setattr(get_settings(), "WEB_DIST_DIR", str(dist))
    with TestClient(create_app()) as c:
        assert "SEGREDO" not in c.get("/%2e%2e/segredo.txt").text
        assert "SEGREDO" not in c.get("/../segredo.txt").text
        assert c.get("/ok.txt").text == "ok"
        r = c.get("/qualquer/rota")
        assert "painel" in r.text and r.headers["Cache-Control"] == "no-cache"
        r = c.get("/api/v1/nao-existe")
        assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")


# ---------- erros de integridade ----------

@pytest.mark.parametrize("sqlstate,status", [("23505", 409), ("23503", 409), ("23514", 422), ("23502", 422), ("XX000", 500)])
def test_integrity_errors_are_classified(client, admin_headers, monkeypatch, sqlstate, status):
    class Orig(Exception):
        pass

    orig = Orig("x")
    orig.sqlstate = sqlstate

    def boom(*a, **k):
        raise IntegrityError("INSERT", {}, orig)

    monkeypatch.setattr(users_service, "create_user", boom)
    body = {"nome": "Novo", "email": "novo@teste.com.br", "senha": "senha-nova-123"}
    r = client.post("/api/v1/users", json=body, headers=admin_headers)
    assert r.status_code == status


# ---------- bordas ----------

def test_bearer_header_edge_cases(client, admin):
    headers = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    token = headers["Authorization"].split()[1]
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "bearer " + token}).status_code == 200
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer  " + token + "  "}).status_code == 200


def test_pagination_params(client, admin_headers, staff):
    assert client.get("/api/v1/users?page=0", headers=admin_headers).status_code == 422
    assert client.get("/api/v1/users?page_size=0", headers=admin_headers).status_code == 422
    assert client.get("/api/v1/users?page=abc", headers=admin_headers).status_code == 422
    r = client.get("/api/v1/users?page=2&page_size=1", headers=admin_headers)
    assert r.status_code == 200 and r.json()["total"] == 2 and len(r.json()["items"]) == 1


def test_must_change_password_scope(client, admin, db):
    admin.must_change_password = True
    db.commit()
    headers = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    assert client.patch("/api/v1/users/me", json={"nome": "Bloqueado"}, headers=headers).status_code == 403
    assert client.post("/api/v1/auth/logout-all", headers=headers).status_code == 200  # celular perdido + reset
