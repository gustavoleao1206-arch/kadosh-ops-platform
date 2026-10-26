from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import FORMAS_PAGAMENTO, sql_in


class Payment(Base):
    """Dinheiro que entrou. 'A receber' é calculado (total da OS − pagamentos não estornados).

    Lançamento errado é estornado (estornado_em), nunca apagado — o rastro fica.
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("valor_centavos > 0", name="valor_positivo"),
        CheckConstraint(f"forma IN ({sql_in(FORMAS_PAGAMENTO)})", name="forma_valida"),
        Index("ix_payments_work_order_id", "work_order_id"),
        Index("ix_payments_pago_em", "pago_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="RESTRICT"), nullable=False)
    valor_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    forma: Mapped[str] = mapped_column(String(15), nullable=False)
    # Editável: Pix de ontem lançado hoje.
    pago_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    observacao: Mapped[str | None] = mapped_column(Text)
    # Chave enviada pelo aparelho: se o sinal cair e o sócio tocar de novo, não duplica.
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)

    estornado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estorno_motivo: Mapped[str | None] = mapped_column(Text)
    estornado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    work_order: Mapped["WorkOrder"] = relationship("WorkOrder", back_populates="payments")

    @property
    def estornado(self) -> bool:
        return self.estornado_em is not None
