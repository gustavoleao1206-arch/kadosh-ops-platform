from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Vehicle(TimestampMixin, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        Index("ix_vehicles_client_id", "client_id"),
        # Placa única só entre veículos ativos com placa — carro 0 km pode não ter,
        # e um carro vendido pode ser recadastrado para o novo dono após arquivar o antigo.
        Index(
            "uq_vehicles_placa_ativa",
            "placa",
            unique=True,
            postgresql_where=text("placa IS NOT NULL AND arquivado_em IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False)
    # Normalizada: maiúsculas, sem hífen ou espaço (antiga ABC1234 ou Mercosul ABC1D23).
    placa: Mapped[str | None] = mapped_column(String(7))
    marca: Mapped[str | None] = mapped_column(String(60))
    modelo: Mapped[str] = mapped_column(String(80), nullable=False)
    cor: Mapped[str | None] = mapped_column(String(40))
    ano: Mapped[int | None] = mapped_column(SmallInteger)
    observacoes: Mapped[str | None] = mapped_column(Text)
    arquivado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client: Mapped["Client"] = relationship("Client", back_populates="vehicles")  # noqa: F821

    @property
    def descricao(self) -> str:
        """'Civic EX Prata · BRA2E19' ou 'Civic EX Prata (sem placa)'."""
        base = " ".join(p for p in (self.marca, self.modelo, self.cor) if p)
        return f"{base} · {self.placa}" if self.placa else f"{base} (sem placa)"
