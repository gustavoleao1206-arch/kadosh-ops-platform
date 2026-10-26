from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ClientServicePrice(TimestampMixin, Base):
    """Preço combinado com UM cliente para UM serviço. Extensão do catálogo, editável só pelo admin.

    Vale para as PRÓXIMAS OS: o valor entra no item no momento do lançamento e congela ali
    (WorkOrderItem.valor_centavos). Mudar ou apagar este preço amanhã não mexe em nenhuma OS nem em
    nenhum relatório de ontem — é por isso que não existe histórico aqui: quem guarda o histórico é
    o item da OS, que é imutável por construção.
    """

    __tablename__ = "client_service_prices"
    __table_args__ = (
        CheckConstraint("valor_centavos >= 0", name="valor_nao_negativo"),
        # sem nome explícito: a convenção de nomes do Base gera
        # "uq_client_service_prices_client_id", que é o nome que a migration cria. Batizar aqui
        # à mão faria o `alembic check` do CI acusar diferença entre modelo e banco para sempre.
        UniqueConstraint("client_id", "service_id"),
        Index("ix_client_service_prices_client_id", "client_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    valor_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
