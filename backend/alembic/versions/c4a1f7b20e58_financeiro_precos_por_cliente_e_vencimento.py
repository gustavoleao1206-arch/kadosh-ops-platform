"""financeiro: precos por cliente e vencimento da cobranca

Revision ID: c4a1f7b20e58
Revises: 7e64046ec973
Create Date: 2026-09-07 21:40:00

Três coisas, todas escritas à mão (o autogenerate não compara CHECK constraints):

1. `client_service_prices` — quanto CADA cliente paga em CADA serviço. Sem histórico próprio de
   propósito: o valor é copiado para o item no lançamento, então o passado já está guardado onde
   importa e mexer aqui nunca reescreve uma OS fechada.

2. `work_orders.vencimento` — a data-limite para receber. Nula em quase toda OS. O índice é PARCIAL
   porque só a régua de cobrança consulta esta coluna, e indexar milhares de NULLs seria pagar
   escrita para não ler nada.

3. O evento 'vencimento' na lista de tipos, para o de/para do prazo ficar no histórico da OS.

ATENÇÃO ao aplicar em base com dados: a partir desta migration, OS já CONCLUÍDAS com saldo em
aberto e sem vencimento passam a aparecer como ATRASADAS. Não é bug — é a regra "entregou sem
receber grita" olhando para trás. Para tirar uma delas do vermelho, defina o vencimento combinado.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c4a1f7b20e58'
down_revision: Union[str, None] = '7e64046ec973'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVENTOS_ANTES = "'status', 'desconto', 'item', 'pagamento', 'reabertura', 'remarcacao', 'transferencia', 'entrada'"
EVENTOS_DEPOIS = EVENTOS_ANTES + ", 'vencimento'"
CK_EVENTOS = "ck_work_order_events_tipo_valido"


def _recria_check_eventos(valores: str) -> None:
    op.execute(f"ALTER TABLE work_order_events DROP CONSTRAINT IF EXISTS {CK_EVENTOS}")
    op.execute(f"ALTER TABLE work_order_events ADD CONSTRAINT {CK_EVENTOS} CHECK (tipo IN ({valores}))")


def upgrade() -> None:
    op.create_table(
        'client_service_prices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('valor_centavos', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('valor_centavos >= 0', name=op.f('ck_client_service_prices_valor_nao_negativo')),
        # CASCADE nos dois lados: sem cliente ou sem serviço, o combinado não quer dizer nada.
        # Seguro porque o histórico não depende desta tabela — depende do item já lançado.
        sa.ForeignKeyConstraint(
            ['client_id'], ['clients.id'],
            name=op.f('fk_client_service_prices_client_id_clients'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['service_id'], ['services.id'],
            name=op.f('fk_client_service_prices_service_id_services'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.id'],
            name=op.f('fk_client_service_prices_created_by_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_client_service_prices')),
        # um preço por par: o upsert do serviço depende deste UNIQUE para não criar linha gêmea
        sa.UniqueConstraint('client_id', 'service_id', name=op.f('uq_client_service_prices_client_id')),
    )
    op.create_index('ix_client_service_prices_client_id', 'client_service_prices', ['client_id'])

    op.add_column('work_orders', sa.Column('vencimento', sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        'ix_work_orders_vencimento',
        'work_orders',
        ['vencimento'],
        postgresql_where=sa.text('vencimento IS NOT NULL'),
    )

    _recria_check_eventos(EVENTOS_DEPOIS)


def downgrade() -> None:
    op.execute("DELETE FROM work_order_events WHERE tipo = 'vencimento'")
    _recria_check_eventos(EVENTOS_ANTES)
    op.drop_index('ix_work_orders_vencimento', table_name='work_orders')
    op.drop_column('work_orders', 'vencimento')
    op.drop_index('ix_client_service_prices_client_id', table_name='client_service_prices')
    op.drop_table('client_service_prices')
