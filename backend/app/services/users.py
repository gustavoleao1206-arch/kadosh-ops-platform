"""Regras de usuários (só admin): criar, alterar, desativar, resetar senha.

Regras fixas: ninguém altera o próprio papel nem desativa a si mesmo; depois de qualquer alteração
deve restar ao menos um administrador ativo (checado após a mudança, com lock nos admins).
Fronteira de transação: cada função pública é uma transação.
"""

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import AuthSession, User
from app.services.auth import _now, log_event


class UserRuleError(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def count_active_admins(db: Session) -> int:
    return (
        db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))) or 0
    )


def create_user(
    db: Session,
    *,
    nome: str,
    email: str,
    senha: str,
    role: str,
    actor: User | None = None,
    must_change_password: bool = False,
    ip: str | None = None,
    user_agent: str | None = None,
) -> User:
    if db.scalar(select(User.id).where(User.email == email)):
        raise UserRuleError("Já existe um usuário com este e-mail.", 409)
    user = User(
        nome=nome,
        email=email,
        password_hash=hash_password(senha),
        role=role,
        is_active=True,
        must_change_password=must_change_password,
    )
    db.add(user)
    db.flush()
    log_event(db, "usuario_criado", actor.id if actor else None, ip, user_agent, target_user_id=user.id)
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    target: User,
    *,
    actor: User,
    nome: str | None,
    role: str | None,
    is_active: bool | None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> User:
    if target.id == actor.id and role is not None and role != target.role:
        raise UserRuleError("Você não pode alterar o próprio papel.", 403)
    if target.id == actor.id and is_active is False:
        raise UserRuleError("Você não pode desativar a si mesmo.", 403)

    # Lock nos admins: dois admins rebaixando um ao outro ao mesmo tempo não podem deixar zero.
    db.execute(select(User.id).where(User.role == "admin").with_for_update())

    changes: list[str] = []
    if nome is not None and nome != target.nome:
        target.nome = nome
        changes.append("nome")
    if role is not None and role != target.role:
        changes.append(f"role:{target.role}->{role}")
        target.role = role
    if is_active is not None and is_active != target.is_active:
        changes.append(f"is_active:{target.is_active}->{is_active}")
        target.is_active = is_active
        if is_active is False:
            db.execute(
                update(AuthSession)
                .where(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None))
                .values(revoked_at=_now())
            )
    db.flush()

    if count_active_admins(db) == 0:
        db.rollback()
        raise UserRuleError("Deve restar ao menos um administrador ativo; crie outro antes.", 409)

    if changes:
        log_event(db, "usuario_alterado", actor.id, ip, user_agent, target_user_id=target.id)
    db.commit()
    db.refresh(target)
    return target


def reset_password(
    db: Session,
    target: User,
    *,
    actor: User | None,
    senha_nova: str,
    ip: str | None,
    user_agent: str | None,
) -> None:
    """Define uma senha temporária; o usuário é obrigado a trocar no próximo login. Não reativa usuário."""
    target.password_hash = hash_password(senha_nova)
    target.must_change_password = True
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    log_event(db, "senha_resetada", actor.id if actor else None, ip, user_agent, target_user_id=target.id)
    db.commit()
