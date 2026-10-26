"""Matriz endpoint × papel. Cada linha é uma garantia de que a autorização vive no backend."""

import pytest
from sqlalchemy import select

from app.models import AuthLog
from tests.conftest import login_android

NEW_USER = {"nome": "Novo", "email": "novo@teste.com.br", "senha": "senha-nova-123", "role": "staff"}

# (método, caminho, corpo, status esperado admin, status esperado staff)
MATRIX = [
    ("GET", "/api/v1/auth/me", None, 200, 200),
    ("PATCH", "/api/v1/users/me", {"nome": "Renomeado"}, 200, 200),
    ("GET", "/api/v1/users", None, 200, 403),
    ("POST", "/api/v1/users", NEW_USER, 201, 403),
    ("PATCH", "/api/v1/users/{other_id}", {"nome": "Xis"}, 200, 403),
    ("POST", "/api/v1/users/{other_id}/reset-password", {"senha_nova": "senha-temp-1234"}, 200, 403),
    ("POST", "/api/v1/users/{other_id}/logout-all", None, 200, 403),
]


@pytest.mark.parametrize("method,path,body,admin_status,staff_status", MATRIX)
def test_matrix(client, admin, staff, method, path, body, admin_status, staff_status):
    # Loga os dois ANTES de agir: a ação do admin pode invalidar a senha/sessão do staff (reset, logout-all).
    headers = {
        admin.id: login_android(client, admin.email, "senha-admin-123"),
        staff.id: login_android(client, staff.email, "senha-staff-123"),
    }
    # staff primeiro: a negação (403) não altera nada; depois o admin executa de verdade.
    for role_user, expected in ((staff, staff_status), (admin, admin_status)):
        other = staff if role_user is admin else admin
        url = path.format(other_id=other.id)
        r = client.request(method, url, json=body, headers=headers[role_user.id])
        assert r.status_code == expected, f"{role_user.role} {method} {url} -> {r.status_code}: {r.text}"


def test_denied_access_is_logged(client, staff, db):
    headers = login_android(client, staff.email, "senha-staff-123")
    assert client.get("/api/v1/users", headers=headers).status_code == 403
    events = [l.evento for l in db.scalars(select(AuthLog)).all()]
    assert "acesso_negado" in events
