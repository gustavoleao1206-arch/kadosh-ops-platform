from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Service(TimestampMixin, Base):
    """Catálogo de serviços. Editável só pelo admin."""

    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("valor_base_centavos >= 0", name="valor_base_nao_negativo"),
        CheckConstraint("duracao_estimada_min >= 0", name="duracao_nao_negativa"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    valor_base_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duracao_estimada_min: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
