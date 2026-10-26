"""Comandos de manutenção (rodam no Shell do Render ou localmente):

    python -m app.cli reset-password <email>      gera senha temporária e imprime uma vez (não reativa usuário)
    python -m app.cli create-user <nome> <email> [admin|staff]
    python -m app.cli purge-sessions              apaga sessões revogadas/expiradas há mais de 30 dias
    python -m app.cli seed-demo                   dados de demonstração (recusa em produção)
"""

import secrets
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import User
from app.services import auth as auth_service
from app.services import users as users_service


def _reset_password(email: str) -> int:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if not user:
            print(f"Usuário não encontrado: {email}")
            return 1
        temp = secrets.token_urlsafe(9)
        users_service.reset_password(db, user, actor=None, senha_nova=temp, ip=None, user_agent="cli")
        ativo = "ativo" if user.is_active else "DESATIVADO (continua sem acesso até ser reativado no painel)"
    print(f"Senha temporária de {email}: {temp}")
    print(f"Usuário {ativo}. Deverá trocar a senha no próximo login. Todas as sessões foram encerradas.")
    print("Limpe o histórico do terminal depois de anotar a senha.")
    return 0


def _create_user(nome: str, email: str, role: str = "staff") -> int:
    if role not in ("admin", "staff"):
        print("Papel deve ser admin ou staff.")
        return 1
    temp = secrets.token_urlsafe(9)
    with SessionLocal() as db:
        try:
            users_service.create_user(
                db, nome=nome, email=email.lower(), senha=temp, role=role, must_change_password=True, user_agent="cli"
            )
        except users_service.UserRuleError as e:
            print(e.detail)
            return 1
    print(f"Usuário {email} criado ({role}). Senha temporária: {temp}")
    return 0


def _purge_sessions() -> int:
    with SessionLocal() as db:
        n = auth_service.purge_sessions(db)
    print(f"{n} sessão(ões) antiga(s) removida(s).")
    return 0


def _seed_demo() -> int:
    settings = get_settings()
    if settings.is_production:
        print("Seed de demonstração NÃO roda em produção.")
        return 1
    from app.seed import seed_demo

    seed_demo()
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 1:
        print(__doc__)
        return 1
    cmd, *args = argv
    if cmd == "reset-password" and len(args) == 1:
        return _reset_password(args[0])
    if cmd == "create-user" and len(args) in (2, 3):
        return _create_user(*args)
    if cmd == "purge-sessions":
        return _purge_sessions()
    if cmd == "seed-demo":
        return _seed_demo()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
