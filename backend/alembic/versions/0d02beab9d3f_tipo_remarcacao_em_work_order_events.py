"""tipo remarcacao em work_order_events

Revision ID: 0d02beab9d3f
Revises: bb6123033d89
Create Date: 2026-08-21 13:45:00

O autogenerate do Alembic não compara CHECK constraints — esta migration é escrita à mão.
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0d02beab9d3f'
down_revision: Union[str, None] = 'bb6123033d89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ANTES = "'status', 'desconto', 'item', 'pagamento', 'reabertura', 'transferencia'"
DEPOIS = "'status', 'desconto', 'item', 'pagamento', 'reabertura', 'remarcacao', 'transferencia'"
NOME = "ck_work_order_events_tipo_valido"


def _recria(valores: str) -> None:
    op.execute(f"ALTER TABLE work_order_events DROP CONSTRAINT IF EXISTS {NOME}")
    op.execute(f"ALTER TABLE work_order_events ADD CONSTRAINT {NOME} CHECK (tipo IN ({valores}))")


def upgrade() -> None:
    _recria(DEPOIS)


def downgrade() -> None:
    op.execute("DELETE FROM work_order_events WHERE tipo = 'remarcacao'")
    _recria(ANTES)
