from sqlalchemy import select

from app.models import AuthLog, AuthSession
from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASS,
    SAME_ORIGIN,
    STAFF_EMAIL,
    STAFF_PASS,
    login_android,
    login_web,
)


def test_login_android_returns_token_and_logs(client, admin, db):
    headers = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == ADMIN_EMAIL
    assert r.json()["role"] == "admin"

    sessions = db.scalars(select(AuthSession)).all()
    assert len(sessions) == 1 and sessions[0].client == "android"
    # o token bruto nunca é gravado no banco
    assert sessions[0].token_hash != headers["Authorization"].split()[1]
    events = [l.evento for l in db.scalars(select(AuthLog)).all()]
    assert events == ["login_ok"]


def test_login_web_uses_httponly_cookie(client, admin):
    r = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": ADMIN_PASS, "client": "web"})
    assert r.status_code == 200
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=strict" in set_cookie and "path=/" in set_cookie
    assert r.json()["token"] is None
    assert client.get("/api/v1/auth/me").status_code == 200


def test_login_email_is_case_insensitive(client, admin):
    r = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL.upper(), "senha": ADMIN_PASS, "client": "android"})
    assert r.status_code == 200


def test_login_wrong_password_and_unknown_email(client, admin, db):
    r = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": "errada-errada", "client": "android"})
    assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "ninguem@teste.com.br", "senha": "qualquer", "client": "android"})
    assert r.status_code == 401
    logs = db.scalars(select(AuthLog)).all()
    assert [l.evento for l in logs] == ["login_falha", "login_falha"]
    # e-mail desconhecido: não guarda nada que identifique o que foi digitado
    assert logs[1].user_id is None


def test_inactive_user_cannot_login(client, staff, db):
    staff.is_active = False
    db.commit()
    r = client.post("/api/v1/auth/login", json={"email": STAFF_EMAIL, "senha": STAFF_PASS, "client": "android"})
    assert r.status_code == 401


def test_missing_or_invalid_token(client, admin):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer token-invalido"}).status_code == 401


def test_logout_revokes_session(client, admin):
    headers = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_logout_all_revokes_every_device(client, admin):
    h1 = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    h2 = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    r = client.post("/api/v1/auth/logout-all", headers=h1)
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me", headers=h1).status_code == 401
    assert client.get("/api/v1/auth/me", headers=h2).status_code == 401


def test_change_password_keeps_current_session_and_drops_others(client, admin):
    h_phone = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    h_other = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    r = client.post(
        "/api/v1/auth/change-password",
        json={"senha_atual": ADMIN_PASS, "senha_nova": "nova-senha-segura-1"},
        headers=h_phone,
    )
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/auth/me", headers=h_phone).status_code == 200
    assert client.get("/api/v1/auth/me", headers=h_other).status_code == 401
    # senha antiga não funciona mais; nova funciona
    assert client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": ADMIN_PASS, "client": "android"}).status_code == 401
    login_android(client, ADMIN_EMAIL, "nova-senha-segura-1")


def test_change_password_validations(client, admin_headers):
    r = client.post("/api/v1/auth/change-password", json={"senha_atual": "errada", "senha_nova": "nova-senha-segura-1"}, headers=admin_headers)
    assert r.status_code == 400
    r = client.post("/api/v1/auth/change-password", json={"senha_atual": ADMIN_PASS, "senha_nova": "curta"}, headers=admin_headers)
    assert r.status_code == 422
    r = client.post("/api/v1/auth/change-password", json={"senha_atual": ADMIN_PASS, "senha_nova": ADMIN_PASS}, headers=admin_headers)
    assert r.status_code == 400


def test_must_change_password_blocks_other_routes(client, admin, db):
    admin.must_change_password = True
    db.commit()
    headers = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.get("/api/v1/users", headers=headers).status_code == 403
    r = client.post(
        "/api/v1/auth/change-password",
        json={"senha_atual": ADMIN_PASS, "senha_nova": "nova-senha-segura-1"},
        headers=headers,
    )
    assert r.status_code == 200
    assert client.get("/api/v1/users", headers=headers).status_code == 200


def test_rate_limit_per_ip(client, admin, rate_limit_on):
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": "errada-errada", "client": "android"})
    r = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": ADMIN_PASS, "client": "android"})
    assert r.status_code == 429


def test_rate_limit_per_email_and_source(client, admin):
    from app.core.limiter import login_throttle

    for _ in range(5):  # a partir da 5ª falha entra o atraso progressivo (1 s, 2 s, 4 s…)
        login_throttle.register_failure(ADMIN_EMAIL, "testclient")  # o IP que o TestClient informa
    r = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": ADMIN_PASS, "client": "android"})
    assert r.status_code == 429
    assert r.headers.get("Retry-After")


def test_unknown_fields_are_rejected(client, admin):
    r = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": ADMIN_PASS, "client": "android", "role": "admin"})
    assert r.status_code == 422


class TestCsrf:
    """Autenticação por cookie em métodos que alteram dados exige mesma origem."""

    def test_cookie_post_without_fetch_metadata_is_blocked(self, client, admin):
        login_web(client, ADMIN_EMAIL, ADMIN_PASS)
        r = client.patch("/api/v1/users/me", json={"nome": "Novo Nome"})
        assert r.status_code == 403

    def test_cookie_post_cross_site_is_blocked(self, client, admin):
        login_web(client, ADMIN_EMAIL, ADMIN_PASS)
        r = client.patch("/api/v1/users/me", json={"nome": "Novo Nome"}, headers={"Sec-Fetch-Site": "cross-site"})
        assert r.status_code == 403

    def test_cookie_post_same_origin_is_allowed(self, client, admin):
        login_web(client, ADMIN_EMAIL, ADMIN_PASS)
        r = client.patch("/api/v1/users/me", json={"nome": "Novo Nome"}, headers=SAME_ORIGIN)
        assert r.status_code == 200
        assert r.json()["nome"] == "Novo Nome"

    def test_cookie_get_needs_no_metadata(self, client, admin):
        login_web(client, ADMIN_EMAIL, ADMIN_PASS)
        assert client.get("/api/v1/auth/me").status_code == 200

    def test_bearer_post_needs_no_metadata(self, client, staff):
        headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
        r = client.patch("/api/v1/users/me", json={"nome": "Sócio"}, headers=headers)
        assert r.status_code == 200
