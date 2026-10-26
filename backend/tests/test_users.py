from app.bootstrap import bootstrap_admin
from app.core.config import get_settings
from tests.conftest import ADMIN_EMAIL, STAFF_EMAIL, STAFF_PASS, login_android


def test_create_user_and_duplicate_email(client, admin_headers):
    body = {"nome": "Novo Sócio", "email": "novo@teste.com.br", "senha": "senha-nova-123", "role": "staff"}
    r = client.post("/api/v1/users", json=body, headers=admin_headers)
    assert r.status_code == 201
    assert r.json()["role"] == "staff" and r.json()["must_change_password"] is False
    r = client.post("/api/v1/users", json=body, headers=admin_headers)
    assert r.status_code == 409


def test_create_user_validations(client, admin_headers):
    r = client.post("/api/v1/users", json={"nome": "X", "email": "nao-e-email", "senha": "senha-nova-123"}, headers=admin_headers)
    assert r.status_code == 422
    r = client.post("/api/v1/users", json={"nome": "Novo", "email": "a@b.co", "senha": "curta"}, headers=admin_headers)
    assert r.status_code == 422
    r = client.post("/api/v1/users", json={"nome": "Novo", "email": "a@b.co", "senha": "senha-nova-123", "role": "root"}, headers=admin_headers)
    assert r.status_code == 422


def test_list_users_is_paginated(client, admin_headers):
    r = client.get("/api/v1/users?page=1&page_size=10", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["total"] == 1
    assert client.get("/api/v1/users?page_size=500", headers=admin_headers).status_code == 422


def test_cannot_change_own_role_or_deactivate_self(client, admin, admin_headers):
    r = client.patch(f"/api/v1/users/{admin.id}", json={"role": "staff"}, headers=admin_headers)
    assert r.status_code == 403
    r = client.patch(f"/api/v1/users/{admin.id}", json={"is_active": False}, headers=admin_headers)
    assert r.status_code == 403


def test_role_change_applies_to_existing_session_without_relogin(client, admin, staff, admin_headers):
    # promove o staff; o novo admin rebaixa o antigo, cujo token continua o mesmo
    assert client.patch(f"/api/v1/users/{staff.id}", json={"role": "admin"}, headers=admin_headers).status_code == 200
    staff_headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
    assert client.patch(f"/api/v1/users/{admin.id}", json={"role": "staff"}, headers=staff_headers).status_code == 200
    # o rebaixado perde acesso às rotas de admin imediatamente (o papel é lido do banco, não do token)
    assert client.get("/api/v1/users", headers=admin_headers).status_code == 403


def test_sole_admin_cannot_demote_or_deactivate_self(client, admin, staff, admin_headers):
    client.patch(f"/api/v1/users/{staff.id}", json={"role": "admin"}, headers=admin_headers)
    staff_headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
    client.patch(f"/api/v1/users/{admin.id}", json={"is_active": False}, headers=staff_headers)
    # sobrou um admin ativo: ele não pode se rebaixar (próprio papel) nem se desativar
    assert client.patch(f"/api/v1/users/{staff.id}", json={"role": "staff"}, headers=staff_headers).status_code == 403
    assert client.patch(f"/api/v1/users/{staff.id}", json={"is_active": False}, headers=staff_headers).status_code == 403


def test_service_refuses_to_remove_last_active_admin(db, admin, staff):
    """Invariante no serviço (a CLI e rotas futuras também passam por aqui): deve restar um admin ativo."""
    import pytest

    from app.services import users as users_service

    with pytest.raises(users_service.UserRuleError) as e:
        users_service.update_user(db, admin, actor=staff, nome=None, role="staff", is_active=None)
    assert e.value.status_code == 409
    with pytest.raises(users_service.UserRuleError):
        users_service.update_user(db, admin, actor=staff, nome=None, role=None, is_active=False)
    db.rollback()
    assert users_service.count_active_admins(db) == 1


def test_admin_changes_are_logged_with_target(client, admin, staff, admin_headers, db):
    from sqlalchemy import select

    from app.models import AuthLog

    client.patch(f"/api/v1/users/{staff.id}", json={"nome": "Sócio Renomeado"}, headers=admin_headers)
    log = db.scalar(select(AuthLog).where(AuthLog.evento == "usuario_alterado"))
    assert log is not None and log.user_id == admin.id and log.target_user_id == staff.id


def test_deactivating_user_revokes_sessions(client, admin_headers, staff):
    staff_headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
    r = client.patch(f"/api/v1/users/{staff.id}", json={"is_active": False}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert client.get("/api/v1/auth/me", headers=staff_headers).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": STAFF_EMAIL, "senha": STAFF_PASS, "client": "android"}).status_code == 401


def test_reset_password_forces_change_and_revokes(client, admin_headers, staff):
    staff_headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
    r = client.post(f"/api/v1/users/{staff.id}/reset-password", json={"senha_nova": "temporaria-123"}, headers=admin_headers)
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me", headers=staff_headers).status_code == 401
    new_headers = login_android(client, STAFF_EMAIL, "temporaria-123")
    me = client.get("/api/v1/auth/me", headers=new_headers).json()
    assert me["must_change_password"] is True
    assert client.get("/api/v1/users", headers=new_headers).status_code == 403


def test_admin_logout_all_for_user(client, admin_headers, staff):
    staff_headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
    r = client.post(f"/api/v1/users/{staff.id}/logout-all", headers=admin_headers)
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me", headers=staff_headers).status_code == 401


def test_user_not_found(client, admin_headers):
    assert client.patch("/api/v1/users/9999", json={"nome": "Xis"}, headers=admin_headers).status_code == 404


def test_bootstrap_creates_admin_only_when_empty(db, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "Boot@Teste.com.br")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "senha-boot-12345")
    assert bootstrap_admin() is True
    from sqlalchemy import select

    from app.models import User

    user = db.scalar(select(User).where(User.email == "boot@teste.com.br"))
    assert user is not None and user.role == "admin" and user.must_change_password is True
    old_hash = user.password_hash
    # segunda chamada: tabela não está vazia → não cria nem altera
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "outra-senha-12345")
    assert bootstrap_admin() is False
    db.refresh(user)
    assert user.password_hash == old_hash


def test_bootstrap_ignores_short_password(db, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "curta")
    assert bootstrap_admin() is False
