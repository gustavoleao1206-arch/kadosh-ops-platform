"""idempotencia no item da OS

Revision ID: 7e64046ec973
Revises: a7f2c4e91b30
Create Date: 2026-09-07 04:10:00

Lançar serviço era a única mutação que criava valor do nada num toque repetido: o mesmo serviço
entrava duas vezes e o total da OS dobrava. Recepção e pagamento já tinham chave; o item não.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '7e64046ec973'
down_revision: Union[str, None] = 'a7f2c4e91b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('work_order_items', sa.Column('idempotency_key', sa.String(length=64), nullable=True))
    op.create_unique_constraint(op.f('uq_work_order_items_idempotency_key'), 'work_order_items', ['idempotency_key'])


def downgrade() -> None:
    op.drop_constraint(op.f('uq_work_order_items_idempotency_key'), 'work_order_items', type_='unique')
    op.drop_column('work_order_items', 'idempotency_key')
