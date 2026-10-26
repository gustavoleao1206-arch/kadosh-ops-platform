"""Dinheiro que entrou. Uma OS, vários pagamentos; "a receber" é sempre calculado.

Regras da fase:
- Só se lança pagamento a partir da recepção do veículo (STATUSES_ACEITAM_PAGAMENTO). Um sinal pago
  por Pix antes da chegada é lançado na recepção com `pago_em` retroativo — o caixa soma pela data
  em que o dinheiro entrou, não pela data em que alguém digitou.
- Não existe UPDATE nem DELETE de pagamento: valor, forma ou data errados se corrigem estornando e
  lançando de novo. O rastro é o produto.
- Estorno: o autor mexe no que ele mesmo lançou; qualquer outro, só o administrador.
- Fronteira de transação: `registrar` e `estornar` comitam; o resto só lê ou dá flush.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Client, Payment, User, WorkOrder
from app.models.enums import (
    FORMAS_PAGAMENTO,
    FORMAS_PAGAMENTO_LABELS,
    STATUSES_ACEITAM_PAGAMENTO,
    STATUSES_NO_PATIO,
)
from app.services import billing
from app.services import work_orders as wo_service
from app.services.periods import day_bounds, today_local
from app.services.work_orders import WorkOrderError, pago_centavos, reais


def pode_estornar(payment: Payment, user: User) -> bool:
    """Quem lançou desfaz o próprio lançamento; o resto é do administrador."""
    if payment.estornado_em is not None:
        return False
    return user.is_admin or payment.created_by == user.id


def formas() -> list[dict]:
    """As formas de pagamento com rótulo pronto — o painel e o app não guardam texto nenhum."""
    return [{"valor": f, "label": FORMAS_PAGAMENTO_LABELS[f]} for f in FORMAS_PAGAMENTO]


def _linha_lancamento(p: Payment, w: WorkOrder, c: Client) -> dict:
    """Um lançamento como o caixa e o extrato mostram. UMA montagem só: as duas telas alimentam o
    mesmo schema (CaixaLancamentoOut), e manter dois dicionários gêmeos garantiria que um dia
    ganhassem colunas diferentes para a mesma linha."""
    return {
        "id": p.id,
        "work_order_id": w.id,
        "numero": w.numero,
        "cliente_nome": c.nome,
        "valor_centavos": p.valor_centavos,
        "forma": p.forma,
        "forma_label": FORMAS_PAGAMENTO_LABELS.get(p.forma, p.forma),
        "pago_em": p.pago_em,
        "created_at": p.created_at,
        "observacao": p.observacao,
        "estornado_em": p.estornado_em,
        "estorno_motivo": p.estorno_motivo,
    }


def _lancamentos_stmt(*filtros):
    """Os lançamentos de uma janela, do mais recente para o mais antigo, com OS e cliente juntos."""
    return (
        select(Payment, WorkOrder, Client)
        .join(WorkOrder, WorkOrder.id == Payment.work_order_id)
        .join(Client, Client.id == WorkOrder.client_id)
        .where(*filtros)
        .order_by(Payment.pago_em.desc(), Payment.id.desc())
    )


def por_forma(db: Session, *filtros) -> list[dict]:
    """Quebra do recebido por forma, na ordem fixa de FORMAS_PAGAMENTO (a tela não pode dançar).

    Recebe os filtros já prontos para que caixa, extrato e relatório perguntem a MESMA coisa de
    jeitos diferentes sem reescrever o predicado de "recebido".
    """
    somas = dict(
        db.execute(
            select(Payment.forma, func.coalesce(func.sum(Payment.valor_centavos), 0))
            .where(*filtros, Payment.estornado_em.is_(None))
            .group_by(Payment.forma)
        ).all()
    )
    return [
        {"forma": f, "forma_label": FORMAS_PAGAMENTO_LABELS[f], "total_centavos": int(somas[f])}
        for f in FORMAS_PAGAMENTO
        if somas.get(f)
    ]


def _mesma_chave(db: Session, chave: str | None) -> Payment | None:
    if not chave:
        return None
    return db.scalar(select(Payment).where(Payment.idempotency_key == chave))


def registrar(db: Session, work_order_id: int, data: dict, *, user: User) -> WorkOrder:
    """Lança um pagamento na OS. Uma forma por lançamento; Pix + dinheiro são dois lançamentos."""
    chave = data.get("idempotency_key")
    repetido = _mesma_chave(db, chave)
    if repetido is not None:
        # o toque repetido com sinal ruim devolve o mesmo estado, não lança de novo
        if repetido.work_order_id != work_order_id:
            raise WorkOrderError(
                "Este lançamento pertence a outra OS. Feche e abra a tela de pagamento de novo.", 409
            )
        return wo_service.get_work_order(db, work_order_id)  # type: ignore[return-value]

    try:
        return _registrar(db, work_order_id, data, user=user, chave=chave)
    except IntegrityError:
        db.rollback()
        # corrida na chave: a primeira requisição ganhou. O UNIQUE estoura no primeiro flush depois
        # da marcação, não só no commit — por isso o try cobre a mutação inteira.
        repetido = _mesma_chave(db, chave)
        if repetido is not None and repetido.work_order_id == work_order_id:
            return wo_service.get_work_order(db, work_order_id)  # type: ignore[return-value]
        raise


def _registrar(db: Session, work_order_id: int, data: dict, *, user: User, chave: str | None) -> WorkOrder:
    wo = wo_service.get_locked(db, work_order_id)

    # Segunda leitura da chave, agora SOB O LOCK. A primeira (em `registrar`) acontece antes de
    # qualquer trava: numa corrida, a requisição gêmea ainda não tinha comitado e passou batido.
    # Aqui o lock já serializou com ela, então a chave dela está visível. Sem isto o retry cairia
    # na validação de saldo e viraria 409 "Esta OS já está paga" — justamente quando o primeiro
    # toque quitou a OS, que é o caso comum (o painel pré-preenche o valor com o saldo inteiro).
    # A rede do UNIQUE não cobre esse caso: as validações rodam antes do INSERT.
    repetido = _mesma_chave(db, chave)
    if repetido is not None:
        if repetido.work_order_id != wo.id:
            raise WorkOrderError(
                "Este lançamento pertence a outra OS. Feche e abra a tela de pagamento de novo.", 409
            )
        return wo_service.get_work_order(db, wo.id)  # type: ignore[return-value]

    if wo.status not in STATUSES_ACEITAM_PAGAMENTO:
        if wo.status in ("cancelado", "nao_compareceu"):
            raise WorkOrderError("Esta OS está encerrada e não recebe pagamento.", 409)
        raise WorkOrderError(
            "Esta OS ainda não recebeu o veículo. O pagamento é lançado a partir da recepção.", 409
        )

    valor = int(data["valor_centavos"])
    falta = wo_service.saldo_em_aberto(db, wo)
    if falta == 0:
        if wo.valor_total_centavos == 0:
            raise WorkOrderError("Lance os serviços antes de receber o pagamento.", 409)
        raise WorkOrderError("Esta OS já está paga.", 409)
    if valor > falta:
        raise WorkOrderError(f"O valor passa do que falta receber nesta OS ({reais(falta)}).", 409)

    pagamento = Payment(
        work_order_id=wo.id,
        valor_centavos=valor,
        forma=data["forma"],
        pago_em=data.get("pago_em") or datetime.now(timezone.utc),
        observacao=data.get("observacao"),
        idempotency_key=chave,
        created_by=user.id,
    )
    db.add(pagamento)
    wo_service._event(db, wo, tipo="pagamento", para=f"{pagamento.forma} {valor}", user=user)
    db.commit()
    return wo_service.get_work_order(db, wo.id)  # type: ignore[return-value]


def estornar(db: Session, work_order_id: int, payment_id: int, *, motivo: str, user: User) -> WorkOrder:
    """Desfaz um lançamento sem apagá-lo. Não olha o status da OS: OS cancelada também devolve."""
    wo = wo_service.get_locked(db, work_order_id)
    pagamento = db.get(Payment, payment_id)
    if pagamento is None or pagamento.work_order_id != wo.id:
        raise WorkOrderError("Pagamento não encontrado nesta OS.", 404)
    if pagamento.estornado_em is not None:
        raise WorkOrderError("Este pagamento já foi estornado.", 409)
    if not (user.is_admin or pagamento.created_by == user.id):
        raise WorkOrderError("Só o administrador estorna um lançamento feito por outra pessoa.", 403)

    pagamento.estornado_em = datetime.now(timezone.utc)
    pagamento.estorno_motivo = motivo
    pagamento.estornado_por = user.id
    wo_service._event(
        db,
        wo,
        tipo="pagamento",
        de=f"{pagamento.forma} {pagamento.valor_centavos}",
        motivo=motivo,
        user=user,
    )
    db.commit()
    return wo_service.get_work_order(db, wo.id)  # type: ignore[return-value]


def recebido_centavos(db: Session, ini: datetime, fim: datetime) -> int:
    """Dinheiro que entrou no intervalo, por `pago_em` e sem os estornados.

    Existe para o predicado de "Recebido" viver num lugar só: o relatório da fase 6 chama esta
    função em vez de repetir o WHERE.
    """
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Payment.valor_centavos), 0)).where(
                Payment.estornado_em.is_(None), Payment.pago_em >= ini, Payment.pago_em < fim
            )
        )
        or 0
    )


# --------------------------------------------------------------------------- caixa do dia


def caixa(db: Session, dia=None) -> dict:
    """Fechamento de um dia: quanto entrou, em quê, quais lançamentos e quem ainda deve.

    O dia é o dia da loja (America/Maceio) e a soma é por `pago_em` — um Pix de ontem lançado hoje
    cai no caixa de ontem, que é onde o dinheiro entrou de verdade.
    """
    alvo = dia or today_local()
    ini, fim = day_bounds(alvo)

    do_dia = (Payment.pago_em >= ini, Payment.pago_em < fim)
    linhas = db.execute(_lancamentos_stmt(*do_dia)).all()
    recebido = sum(p.valor_centavos for p, _, _ in linhas if p.estornado_em is None)
    quebra_por_forma = por_forma(db, *do_dia)

    # quem ainda deve: carro no pátio ou OS concluída com saldo. Uma consulta só, sem N+1.
    pago_por_os = billing.pago_por_os()
    devedores = db.execute(
        select(WorkOrder, Client, func.coalesce(pago_por_os.c.pago, 0))
        .join(Client, Client.id == WorkOrder.client_id)
        .outerjoin(pago_por_os, pago_por_os.c.wid == WorkOrder.id)
        .where(
            WorkOrder.status.in_((*STATUSES_NO_PATIO, "concluido")),
            WorkOrder.valor_total_centavos > func.coalesce(pago_por_os.c.pago, 0),
        )
        .order_by(WorkOrder.conclusao.desc().nullslast(), WorkOrder.entrada, WorkOrder.id)
    ).all()

    agora = datetime.now(timezone.utc)
    return {
        "dia": alvo.isoformat(),
        "recebido_centavos": recebido,
        "por_forma": quebra_por_forma,
        "lancamentos": [_linha_lancamento(p, w, c) for p, w, c in linhas],
        "a_receber_centavos": sum(int(w.valor_total_centavos) - int(pago) for w, _, pago in devedores),
        "a_receber": [
            {
                "work_order_id": w.id,
                "numero": w.numero,
                "cliente_nome": c.nome,
                "status": w.status,
                "status_label": wo_service.WORK_ORDER_STATUS_LABELS.get(w.status, w.status),
                "status_tone": wo_service.STATUS_TONES.get(w.status, "neutral"),
                "valor_total_centavos": w.valor_total_centavos,
                "pago_centavos": int(pago),
                "saldo_centavos": int(w.valor_total_centavos) - int(pago),
                "situacao_cobranca": (sit := billing.situacao(
                    status=w.status,
                    valor_total_centavos=w.valor_total_centavos,
                    pago_centavos=int(pago),
                    vencimento=w.vencimento,
                    agora=agora,
                )),
                "situacao_cobranca_label": billing.label(sit),
                "situacao_cobranca_tone": billing.tone(sit),
                "vencimento": w.vencimento,
            }
            for w, c, pago in devedores
        ],
    }


# --------------------------------------------------------------------------- extrato do período


def extrato(
    db: Session,
    ini: datetime,
    fim: datetime,
    *,
    forma: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Os lançamentos de um intervalo, em ordem de quando o dinheiro entrou.

    É o caixa esticado no tempo, e de propósito responde igualzinho a ele: mesma montagem de linha
    (`_linha_lancamento`), mesma quebra por forma (`por_forma`), soma por `pago_em`, e os estornados
    APARECEM na lista (riscados) mas ficam FORA dos totais. Se as duas telas usassem critérios
    diferentes, o dono somaria a semana no extrato e não bateria com os sete dias do caixa —
    tests/test_financeiro.py fecha essa porta comparando as duas.

    `estornos_centavos` é a soma do que está riscado NESTA janela (e sob o mesmo filtro de forma).
    Existe para conciliar: sem ele, quem confere nota por nota fica com uma diferença sem nome entre
    o bruto que vê e o total que lê.

    Nota sobre estorno: ele mexe no passado — estornar hoje um pagamento de ontem tira o valor do
    dia de ontem, onde o dinheiro tinha entrado. É a leitura certa para uma loja de duas pessoas
    (o dinheiro não entrou de verdade), e é por isso que a linha estornada continua visível.
    """
    filtros = [Payment.pago_em >= ini, Payment.pago_em < fim]
    if forma:
        filtros.append(Payment.forma == forma)

    total_centavos = int(
        db.scalar(
            select(func.coalesce(func.sum(Payment.valor_centavos), 0)).where(
                *filtros, Payment.estornado_em.is_(None)
            )
        )
        or 0
    )
    total_lancamentos = int(db.scalar(select(func.count()).select_from(Payment).where(*filtros)) or 0)
    linhas = db.execute(
        _lancamentos_stmt(*filtros).offset((page - 1) * page_size).limit(page_size)
    ).all()

    return {
        "total_centavos": total_centavos,
        "estornos_centavos": estornos_centavos(db, *filtros),
        "por_forma": por_forma(db, *filtros),
        "lancamentos": [_linha_lancamento(p, w, c) for p, w, c in linhas],
        "total": total_lancamentos,
    }


def por_forma_no_periodo(db: Session, ini: datetime, fim: datetime) -> list[dict]:
    """Quebra do recebido por forma num período — a mesma conta do caixa e do extrato.

    Chama `por_forma` direto. A primeira versão pedia o extrato inteiro só para ficar com esta
    chave do dicionário, e pagava cinco consultas (incluindo um JOIN de três tabelas) para jogar
    quatro fora.
    """
    return por_forma(db, Payment.pago_em >= ini, Payment.pago_em < fim)


def estornos_centavos(db: Session, *filtros) -> int:
    """Quanto foi estornado dentro da janela (por `pago_em`), para conciliação.

    Recebe os filtros prontos: assim o extrato pode passar o recorte por forma junto, e o relatório
    passa só o intervalo — sem duas implementações da mesma soma.
    """
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Payment.valor_centavos), 0)).where(
                *filtros, Payment.estornado_em.is_not(None)
            )
        )
        or 0
    )
