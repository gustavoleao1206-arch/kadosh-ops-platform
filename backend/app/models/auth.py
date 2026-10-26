from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AUTH_EVENTS, SESSION_CLIENTS, sql_in


class AuthSession(Base):
    """Sessão opaca: o banco guarda só o hash do token. Validade deslizante de SESSION_DAYS."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(f"client IN ({sql_in(SESSION_CLIENTS)})", name="client_valido"),
        Index("ix_sessions_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    client: Mapped[str] = mapped_column(String(10), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthLog(Base):
    """Log de autenticação (pedido na seção 16). Não guarda o e-mail digitado — só o usuário, se existir."""

    __tablename__ = "auth_logs"
    __table_args__ = (
        CheckConstraint(f"evento IN ({sql_in(AUTH_EVENTS)})", name="evento_valido"),
        Index("ix_auth_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # quem fez
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # em quem (reset de senha, alteração de papel, sair de todos os aparelhos)
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    evento: Mapped[str] = mapped_column(String(30), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
