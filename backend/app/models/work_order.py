from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Sequence,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import STATUSES_SEM_VEICULO, WORK_ORDER_EVENT_TYPES, WORK_ORDER_STATUSES, sql_in

# Número legível da OS, atribuído só quando o veículo é recebido (orçamentos e agendamentos não consomem).
work_order_numero_seq = Sequence("work_order_numero_seq", start=1, metadata=Base.metadata)


class WorkOrder(TimestampMixin, Base):
    """Orçamento, agendamento e ordem de serviço são a mesma entidade em fases diferentes."""

    __tablename__ = "work_orders"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in(WORK_ORDER_STATUSES)})", name="status_valido"),
        CheckConstraint(
            f"status IN ({sql_in(STATUSES_SEM_VEICULO)}) OR vehicle_id IS NOT NULL",
            name="veiculo_obrigatorio_fora_do_orcamento",
        ),
        CheckConstraint("desconto_centavos >= 0", name="desconto_nao_negativo"),
        CheckConstraint("valor_total_centavos >= 0", name="total_nao_negativo"),
        Index("ix_work_orders_status", "status"),
        Index("ix_work_orders_client_id", "client_id"),
        Index("ix_work_orders_vehicle_id", "vehicle_id"),
        Index("ix_work_orders_scheduled_at", "scheduled_at"),
        Index("ix_work_orders_entrada", "entrada"),
        Index("ix_work_orders_conclusao", "conclusao"),
        # parcial: quase toda OS tem vencimento nulo, e o índice só serve à régua de cobrança
        Index("ix_work_orders_vencimento", "vencimento", postgresql_where=text("vencimento IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[int | None] = mapped_column(Integer, unique=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="recebido")

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entrada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previsao_conclusao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # True = alguém digitou a previsão à mão; o backend para de recalculá-la pelas durações
    previsao_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    conclusao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Data-limite para receber. Nula na esmagadora maioria das OS (paga-se na retirada); só existe
    # quando alguém combinou prazo. Depois dela, com saldo em aberto, a OS conta como ATRASADA.
    vencimento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    desconto_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Desnormalizado: soma dos itens − desconto. Recalculado por uma única função, com lock da linha.
    valor_total_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Estado do carro ao chegar (riscos, pertences, combustível). Após iniciar a execução, só admin edita.
    observacoes_entrada: Mapped[str | None] = mapped_column(Text)
    observacoes: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Chave enviada pelo aparelho na recepção: se o sinal cair e o sócio tocar de novo, não duplica a OS.
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)

    items: Mapped[list["WorkOrderItem"]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan", order_by="WorkOrderItem.id"
    )
    events: Mapped[list["WorkOrderEvent"]] = relationship(
        back_populates="work_order", cascade="all, delete-orphan", order_by="WorkOrderEvent.id"
    )
    # sem cascade: pagamento não some junto com a OS (a FK é RESTRICT, de propósito)
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="work_order", order_by="Payment.id", passive_deletes="all"
    )


class WorkOrderItem(Base):
    """Um serviço dentro da OS. Copia nome e valor do catálogo no momento do lançamento."""

    __tablename__ = "work_order_items"
    __table_args__ = (
        CheckConstraint("valor_centavos >= 0", name="valor_nao_negativo"),
        Index("ix_work_order_items_work_order_id", "work_order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="RESTRICT"), nullable=False)
    descricao: Mapped[str] = mapped_column(String(120), nullable=False)
    valor_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    # Gerada pelo cliente a cada toque em "lançar": sem ela, o toque repetido numa rede ruim
    # duplica o serviço e DOBRA o total da OS — a única mutação que criava valor do nada.
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    work_order: Mapped["WorkOrder"] = relationship(back_populates="items")


class WorkOrderEvent(Base):
    """Quem mudou o quê e quando (status, desconto, item, pagamento). Gravado na mesma transação da mudança."""

    __tablename__ = "work_order_events"
    __table_args__ = (
        CheckConstraint(f"tipo IN ({sql_in(WORK_ORDER_EVENT_TYPES)})", name="tipo_valido"),
        Index("ix_work_order_events_work_order_id_created_at", "work_order_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    de: Mapped[str | None] = mapped_column(String(120))
    para: Mapped[str | None] = mapped_column(String(120))
    motivo: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    work_order: Mapped["WorkOrder"] = relationship(back_populates="events")
