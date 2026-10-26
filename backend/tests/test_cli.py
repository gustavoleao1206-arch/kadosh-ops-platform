"""CLI de manutenção (RUNBOOK) e seed de demonstração."""

import re

from sqlalchemy import func, select

from app import cli
from app.models import AuthLog, Client, Service, User, Vehicle
from app.seed import DEMO_ADMIN, seed_demo
from tests.conftest import STAFF_EMAIL, STAFF_PASS, login_android


def _temp_password(out: str) -> str:
    m = re.search(r"Senha temporária(?: de [^:]+)?: (\S+)", out)
    assert m, out
    return m.group(1)


def test_cli_reset_password_flow(client, staff, db, capsys):
    old = login_android(client, STAFF_EMAIL, STAFF_PASS)
    assert cli.main(["reset-password", STAFF_EMAIL.upper()]) == 0
    temp = _temp_password(capsys.readouterr().out)
    assert client.get("/api/v1/auth/me", headers=old).status_code == 401
    new = login_android(client, STAFF_EMAIL, temp)
    assert client.get("/api/v1/auth/me", headers=new).json()["must_change_password"] is True
    log = db.scalar(select(AuthLog).where(AuthLog.evento == "senha_resetada"))
    assert log is not None and log.user_id is None and log.target_user_id == staff.id
    assert cli.main(["reset-password", "x@y.zz"]) == 1


def test_cli_reset_password_does_not_reactivate(client, staff, db, capsys):
    staff.is_active = False
    db.commit()
    assert cli.main(["reset-password", STAFF_EMAIL]) == 0
    temp = _temp_password(capsys.readouterr().out)
    db.refresh(staff)
    assert staff.is_active is False
    r = client.post("/api/v1/auth/login", json={"email": STAFF_EMAIL, "senha": temp, "client": "android"})
    assert r.status_code == 401


def test_cli_create_user(client, db, capsys):
    assert cli.main(["create-user", "Nome", "novo@teste.com.br", "root"]) == 1
    assert cli.main(["create-user", "Nome", "Novo@Teste.com.br", "staff"]) == 0
    temp = _temp_password(capsys.readouterr().out)
    assert cli.main(["create-user", "Nome", "novo@teste.com.br", "staff"]) == 1
    headers = login_android(client, "novo@teste.com.br", temp)
    assert client.get("/api/v1/auth/me", headers=headers).json()["must_change_password"] is True
    assert db.scalar(select(AuthLog.evento).where(AuthLog.evento == "usuario_criado")) == "usuario_criado"


def test_cli_usage_and_unknown_command(capsys):
    assert cli.main([]) == 1
    assert cli.main(["nada"]) == 1


def test_seed_demo_is_idempotent(client, db):
    seed_demo()
    seed_demo()
    assert db.scalar(select(func.count()).select_from(User)) == 2
    assert db.scalar(select(func.count()).select_from(Service)) == 13
    assert db.scalar(select(func.count()).select_from(Client)) == 5
    assert db.scalar(select(func.count()).select_from(Vehicle)) == 7
    login_android(client, DEMO_ADMIN[1], DEMO_ADMIN[2])
