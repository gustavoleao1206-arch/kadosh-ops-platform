"""Relatórios do período. Só leitura e agregação — nada aqui escreve no banco.

Duas contas convivem de propósito e nunca se somam:

    Faturado = valor_total das OS concluídas, por `conclusao`  (o serviço entregue)
    Recebido = pagamentos não estornados, por `pago_em`        (o dinheiro que entrou)

Elas divergem quando o cliente paga o sinal em agosto e leva o carro em setembro, ou quando leva
devendo. Por isso o Faturado vem decomposto em "quanto disso já entrou" e "quanto ainda falta":
sem essa linha, o dono olha dois números diferentes e acha que o sistema errou.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.models import Client, Payment, Service, WorkOrder, WorkOrderEvent, WorkOrderItem
from app.models.enums import STATUSES_TERMINAIS
from app.services import billing
from app.services.payments import estornos_centavos, por_forma_no_periodo, recebido_centavos
from app.services.periods import meses_ate, month_bounds, now_local, rotulo_mes, to_local

# seg → dom, como a semana de trabalho é lida no balcão
DIAS_SEMANA = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")

# para o eixo do gráfico de evolução: "Set/26"
MESES_CURTOS = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")


def totais(db: Session, ini: datetime, fim: datetime) -> dict:
    """Só os números de topo de um período. Existe separado porque o dashboard precisa deles sem
    pagar por `por_servico` e `por_dia_semana` — e, sobretudo, para que dashboard e relatório NUNCA
    exibam contas diferentes para a mesma pergunta."""
    concluidas = (WorkOrder.status == "concluido", WorkOrder.conclusao >= ini, WorkOrder.conclusao < fim)

    pago = billing.pago_por_os()
    entregue = db.execute(
        select(
            func.count(WorkOrder.id),
            func.coalesce(func.sum(WorkOrder.valor_total_centavos), 0),
            func.coalesce(func.sum(WorkOrder.desconto_centavos), 0),
            # LEAST porque o par (piso de recalc_total, recusa de pagamento acima do saldo) garante
            # pago <= total; se um dia essa invariante cair, o relatório erra para menos, não para mais
            func.coalesce(func.sum(func.least(func.coalesce(pago.c.pago, 0), WorkOrder.valor_total_centavos)), 0),
        )
        .outerjoin(pago, pago.c.wid == WorkOrder.id)
        .where(*concluidas)
    ).one()
    os_concluidas, faturado, descontos, faturado_recebido = (int(x) for x in entregue)

    encerramentos = dict(
        db.execute(
            select(WorkOrderEvent.para, func.count())
            .where(
                WorkOrderEvent.tipo == "status",
                WorkOrderEvent.para.in_(("cancelado", "nao_compareceu")),
                WorkOrderEvent.created_at >= ini,
                WorkOrderEvent.created_at < fim,
            )
            .group_by(WorkOrderEvent.para)
        ).all()
    )

    return {
        "faturado_centavos": faturado,
        "faturado_recebido_centavos": faturado_recebido,
        "faturado_a_receber_centavos": faturado - faturado_recebido,
        "recebido_centavos": recebido_centavos(db, ini, fim),
        "os_concluidas": os_concluidas,
        "ticket_medio_centavos": round(faturado / os_concluidas) if os_concluidas else 0,
        "desconto_centavos": descontos,
        "cancelamentos": int(encerramentos.get("cancelado", 0)),
        "nao_comparecimentos": int(encerramentos.get("nao_compareceu", 0)),
        # o que foi estornado dentro da janela — sem esta linha sobra uma diferença sem nome entre
        # o bruto que o dono confere na mão e o recebido que o sistema mostra
        "estornos_centavos": estornos_centavos(db, Payment.pago_em >= ini, Payment.pago_em < fim),
    }


def relatorio(db: Session, ini: datetime, fim: datetime) -> dict:
    """Os números de um período [ini, fim) — tudo em UTC, como vem de `periods.periodo_bounds`."""
    concluidas = (WorkOrder.status == "concluido", WorkOrder.conclusao >= ini, WorkOrder.conclusao < fim)

    # nome do catálogo, não a descrição congelada no item: serviço renomeado apareceria partido em
    # duas linhas se agrupasse pelo texto
    servicos = db.execute(
        select(
            Service.id,
            Service.nome,
            func.count(WorkOrderItem.id),
            func.coalesce(func.sum(WorkOrderItem.valor_centavos), 0),
        )
        .select_from(WorkOrderItem)
        .join(WorkOrder, WorkOrder.id == WorkOrderItem.work_order_id)
        .join(Service, Service.id == WorkOrderItem.service_id)
        .where(*concluidas)
        .group_by(Service.id, Service.nome)
        .order_by(func.sum(WorkOrderItem.valor_centavos).desc(), Service.nome)
    ).all()

    # o balde de dia da semana é feito em Python com o fuso da loja: `AT TIME ZONE` no WHERE mataria
    # o índice, e o volume aqui é de dezenas de linhas por mês
    dias = {i: {"os": 0, "total": 0} for i in range(7)}
    for conclusao, total in db.execute(
        select(WorkOrder.conclusao, WorkOrder.valor_total_centavos).where(*concluidas)
    ).all():
        local = to_local(conclusao)
        if local is None:
            continue
        balde = dias[local.weekday()]
        balde["os"] += 1
        balde["total"] += int(total)

    return {
        "totais": totais(db, ini, fim),
        # de onde veio o dinheiro do período: a mesma quebra do caixa e do extrato
        "por_forma": por_forma_no_periodo(db, ini, fim),
        "por_servico": [
            {"service_id": sid, "nome": nome, "quantidade": int(qtd), "total_centavos": int(total)}
            for sid, nome, qtd, total in servicos
        ],
        "por_dia_semana": [
            {
                "dia": i,
                "dia_label": DIAS_SEMANA[i],
                "os_concluidas": dias[i]["os"],
                "faturado_centavos": dias[i]["total"],
            }
            for i in range(7)
        ],
    }


def serie_mensal(db: Session, meses: int = 12, ate=None) -> list[dict]:
    """Faturado e recebido mês a mês — a série do gráfico de evolução.

    Duas consultas para N meses, não duas por mês: puxa o intervalo inteiro e distribui em Python
    usando `to_local`, exatamente como o balde de dia da semana já faz. O mês de um pagamento é o
    mês NA LOJA — um Pix de 31/08 às 22h em Maceió é agosto, embora no banco esteja em setembro UTC.
    """
    referencias = meses_ate(ate or now_local().date(), meses)
    ini, _ = month_bounds(referencias[0])
    _, fim = month_bounds(referencias[-1])

    baldes = {(d.year, d.month): {"faturado": 0, "recebido": 0, "os": 0} for d in referencias}

    for conclusao, total in db.execute(
        select(WorkOrder.conclusao, WorkOrder.valor_total_centavos).where(
            WorkOrder.status == "concluido", WorkOrder.conclusao >= ini, WorkOrder.conclusao < fim
        )
    ).all():
        local = to_local(conclusao)
        balde = baldes.get((local.year, local.month)) if local else None
        if balde is not None:
            balde["faturado"] += int(total)
            balde["os"] += 1

    for pago_em, valor in db.execute(
        select(Payment.pago_em, Payment.valor_centavos).where(
            Payment.estornado_em.is_(None), Payment.pago_em >= ini, Payment.pago_em < fim
        )
    ).all():
        local = to_local(pago_em)
        balde = baldes.get((local.year, local.month)) if local else None
        if balde is not None:
            balde["recebido"] += int(valor)

    return [
        {
            "mes": f"{d.year:04d}-{d.month:02d}",
            "label": rotulo_mes(d),
            # rótulo curto para o eixo do gráfico, onde "Setembro de 2026" não cabe
            "label_curto": f"{MESES_CURTOS[d.month - 1]}/{str(d.year)[2:]}",
            "faturado_centavos": baldes[(d.year, d.month)]["faturado"],
            "recebido_centavos": baldes[(d.year, d.month)]["recebido"],
            "os_concluidas": baldes[(d.year, d.month)]["os"],
        }
        for d in referencias
    ]


def tem_historico(db: Session) -> bool:
    """Existe alguma OS concluída, em qualquer época? Separa "loja nova" de "mês parado"."""
    return db.scalar(select(WorkOrder.id).where(WorkOrder.status == "concluido").limit(1)) is not None


def clientes_sumidos(db: Session, dias: int = 90, limite: int = 50) -> dict:
    """Quem já foi cliente e não volta há mais de N dias, do que mais gastou para o que menos.

    Duas exclusões que a lista precisa para não fazer o dono ligar à toa:
    - quem nunca concluiu nada não entra — é cadastro novo, não cliente perdido;
    - quem tem OS viva (orçamento, agendamento ou carro no pátio agora) não entra — a última
      conclusão pode ser de 200 dias atrás e o carro estar na loja neste minuto.

    O relatório termina numa ligação, então vem com telefone. Devolve o total junto com a página:
    cortar em 50 sem dizer que cortou seria esconder cliente.
    """
    corte = now_local() - timedelta(days=dias)
    # alias obrigatório: o SELECT de fora já usa WorkOrder no JOIN, e sem um FROM próprio o
    # SQLAlchemy auto-correlaciona a subquery até ela ficar sem tabela nenhuma
    Aberta = aliased(WorkOrder)
    tem_os_viva = (
        select(Aberta.id)
        .where(Aberta.client_id == Client.id, Aberta.status.not_in(STATUSES_TERMINAIS))
        .exists()
    )
    base = (
        select(
            Client.id,
            Client.nome,
            Client.telefone,
            func.count(WorkOrder.id).label("atendimentos"),
            func.coalesce(func.sum(WorkOrder.valor_total_centavos), 0).label("gasto"),
            func.max(WorkOrder.conclusao).label("ultimo"),
        )
        .join(WorkOrder, WorkOrder.client_id == Client.id)
        .where(Client.arquivado_em.is_(None), WorkOrder.status == "concluido", ~tem_os_viva)
        .group_by(Client.id, Client.nome, Client.telefone)
        .having(func.max(WorkOrder.conclusao) < corte)
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    linhas = db.execute(base.order_by(func.sum(WorkOrder.valor_total_centavos).desc(), Client.nome).limit(limite)).all()

    agora = now_local()
    return {
        "total": int(total),
        "itens": [
            {
                "client_id": cid,
                "nome": nome,
                "telefone": telefone,
                "atendimentos": int(qtd),
                "total_gasto_centavos": int(gasto),
                "ultimo_atendimento": ultimo,
                "dias_sem_voltar": (agora - to_local(ultimo)).days,  # type: ignore[operator]
            }
            for cid, nome, telefone, qtd, gasto, ultimo in linhas
        ],
    }
