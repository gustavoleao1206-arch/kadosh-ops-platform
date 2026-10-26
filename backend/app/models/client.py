from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Client(TimestampMixin, Base):
    __tablename__ = "clients"
    __table_args__ = (Index("ix_clients_telefone", "telefone"),)

    vehicles: Mapped[list["Vehicle"]] = relationship(  # noqa: F821
        "Vehicle", back_populates="client", order_by="Vehicle.id", passive_deletes="all"
    )  # passive_deletes: quem decide é a FK RESTRICT do banco (→ 409), não um UPDATE para NULL

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    # Só dígitos, com DDI (ex.: 5582999999999). Duplicado avisa, não bloqueia (casal com um número).
    telefone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(254))
    observacoes: Mapped[str | None] = mapped_column(Text)
    # Arquivado some das listas e da busca, mas a ficha e o histórico continuam acessíveis.
    arquivado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
