"""A régua de cobrança: pago, a receber, atrasado.

Nada aqui é gravado. A situação de uma OS é uma FUNÇÃO de quatro coisas — status, total, quanto já
entrou e a data-limite — e o motivo de não existir coluna é este: uma OS vira "atrasada" sozinha à
meia-noite, sem ninguém tocar na linha. Coluna gravada envelheceria mentindo.

A regra existe duas vezes de propósito, porque os dois lados precisam dela em linguagens diferentes:
`situacao()` em Python, para a resposta da API, e `situacao_sql()` em SQL, para filtrar e agregar
sem trazer o banco inteiro para a memória. Divergir seria o pior bug possível do módulo — o filtro
"atrasados" mostrando uma OS que a tela dela chama de "a receber". Por isso tests/test_cobranca.py
roda as duas sobre a mesma matriz de casos e exige resultado idêntico; se você mexer numa, mexa na
outra e o teste cobra.

Este módulo importa só modelos e períodos: é ele que quebra o ciclo entre work_orders e payments,
que precisam ambos da mesma conta.
"""

from datetime import datetime

from sqlalchemy import ColumnElement, and_, case, func, null, select
from sqlalchemy.orm import Session

from app.models import Payment, WorkOrder
from app.models.enums import (
    SITUACAO_COBRANCA_LABELS,
    SITUACAO_COBRANCA_TONES,
    STATUSES_ACEITAM_PAGAMENTO,
)


def pago_por_os():
    """Subquery com quanto já entrou em cada OS (sem os estornados).

    Uma definição só para o caixa, o extrato, o relatório e a régua de cobrança: se cada consulta
    escrevesse o próprio SUM, bastaria uma esquecer o `estornado_em IS NULL` para o dono ver dois
    números diferentes para a mesma pergunta.
    """
    return (
        select(Payment.work_order_id.label("wid"), func.sum(Payment.valor_centavos).label("pago"))
        .where(Payment.estornado_em.is_(None))
        .group_by(Payment.work_order_id)
        .subquery()
    )


def situacao(
    *,
    status: str,
    valor_total_centavos: int,
    pago_centavos: int,
    vencimento: datetime | None,
    agora: datetime,
) -> str | None:
    """A situação de cobrança de UMA OS, em Python. `None` = esta OS não é uma cobrança.

    Ficam de fora as OS que ainda não podem receber dinheiro (orçamento, agendamento) e as
    encerradas sem entrega (cancelada, não compareceu) — e também a OS de total zero, que não é
    dívida nenhuma. Só quem pode receber entra na régua.

    A regra do atraso tem duas portas:
    - venceu o prazo combinado e ainda falta dinheiro;
    - ou o carro FOI ENTREGUE (concluído) sem prazo nenhum e ainda falta dinheiro. Entregar sem
      receber e sem combinar data é exatamente o caso que precisa gritar. Quando havia combinado,
      basta pôr a data no vencimento: a OS volta para "a receber" até o prazo chegar.
    """
    if status not in STATUSES_ACEITAM_PAGAMENTO or valor_total_centavos <= 0:
        return None
    if valor_total_centavos - pago_centavos <= 0:
        return "pago"
    if vencimento is not None:
        return "atrasado" if vencimento < agora else "pendente"
    return "atrasado" if status == "concluido" else "pendente"


def situacao_sql(pago_col, *, agora: datetime) -> ColumnElement:
    """A MESMA regra em SQL, sobre a coluna `pago` de `pago_por_os()`. Serve a filtro e a GROUP BY."""
    saldo = WorkOrder.valor_total_centavos - func.coalesce(pago_col, 0)
    return case(
        (WorkOrder.status.not_in(STATUSES_ACEITAM_PAGAMENTO), null()),
        (WorkOrder.valor_total_centavos <= 0, null()),
        (saldo <= 0, "pago"),
        (and_(WorkOrder.vencimento.is_not(None), WorkOrder.vencimento < agora), "atrasado"),
        (WorkOrder.vencimento.is_not(None), "pendente"),
        (WorkOrder.status == "concluido", "atrasado"),
        else_="pendente",
    )


def saldo_sql(pago_col) -> ColumnElement:
    """Quanto falta receber, nunca negativo (o piso de recalc_total garante, o GREATEST reforça)."""
    return func.greatest(WorkOrder.valor_total_centavos - func.coalesce(pago_col, 0), 0)


def label(sit: str | None) -> str | None:
    return SITUACAO_COBRANCA_LABELS.get(sit) if sit else None


def tone(sit: str | None) -> str | None:
    return SITUACAO_COBRANCA_TONES.get(sit) if sit else None


def resumo(db: Session, agora: datetime) -> dict:
    """Quantas OS e quanto dinheiro há em cada situação — os cartões de cobrança do dashboard."""
    pago = pago_por_os()
    sit = situacao_sql(pago.c.pago, agora=agora)
    saldo = saldo_sql(pago.c.pago)
    linhas = db.execute(
        select(sit.label("situacao"), func.count(), func.coalesce(func.sum(saldo), 0))
        .select_from(WorkOrder)
        .outerjoin(pago, pago.c.wid == WorkOrder.id)
        .group_by(sit)
    ).all()
    por_situacao = {s: (int(qtd), int(total)) for s, qtd, total in linhas if s is not None}
    return {
        s: {"qtd": por_situacao.get(s, (0, 0))[0], "total_centavos": por_situacao.get(s, (0, 0))[1]}
        for s in ("pendente", "atrasado", "pago")
    }
