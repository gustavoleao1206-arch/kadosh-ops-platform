"""laudo de entrada como evento e cancelar orcamento sem veiculo

Revision ID: a7f2c4e91b30
Revises: cebd6c916c32
Create Date: 2026-08-22 00:20:00

Duas correções da revisão da fase 4, ambas em CHECK constraints (que o autogenerate do Alembic
não compara — esta migration é escrita à mão):

1. work_order_events.tipo ganha "entrada": alterar o estado do carro na chegada passa a virar
   linha no histórico, com o texto anterior guardado.
2. work_orders exigia veículo em tudo que não fosse orçamento. Um orçamento recusado nunca teve
   carro e precisava ser cancelado — o CHECK travava e a OS ficava presa para sempre.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a7f2c4e91b30'
down_revision: Union[str, None] = 'cebd6c916c32'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVENTOS = "ck_work_order_events_tipo_valido"
EVENTOS_ANTES = "'status', 'desconto', 'item', 'pagamento', 'reabertura', 'remarcacao', 'transferencia'"
EVENTOS_DEPOIS = "'status', 'desconto', 'item', 'pagamento', 'reabertura', 'remarcacao', 'transferencia', 'entrada'"

VEICULO = "ck_work_orders_veiculo_obrigatorio_fora_do_orcamento"
VEICULO_ANTES = "status = 'orcamento' OR vehicle_id IS NOT NULL"
VEICULO_DEPOIS = "status IN ('orcamento', 'cancelado') OR vehicle_id IS NOT NULL"


def _recria(tabela: str, nome: str, condicao: str) -> None:
    op.execute(f"ALTER TABLE {tabela} DROP CONSTRAINT IF EXISTS {nome}")
    op.execute(f"ALTER TABLE {tabela} ADD CONSTRAINT {nome} CHECK ({condicao})")


def upgrade() -> None:
    _recria("work_order_events", EVENTOS, f"tipo IN ({EVENTOS_DEPOIS})")
    _recria("work_orders", VEICULO, VEICULO_DEPOIS)


def downgrade() -> None:
    # o CHECK antigo recusa OS cancelada sem veículo: volta para orçamento antes de restaurá-lo
    op.execute("UPDATE work_orders SET status = 'orcamento' WHERE status = 'cancelado' AND vehicle_id IS NULL")
    _recria("work_orders", VEICULO, VEICULO_ANTES)
    op.execute("DELETE FROM work_order_events WHERE tipo = 'entrada'")
    _recria("work_order_events", EVENTOS, f"tipo IN ({EVENTOS_ANTES})")
