from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.core.deps import DB, AdminUser, Auth
from app.models import Client, Vehicle, WorkOrder
from app.models.enums import (
    FORMAS_PAGAMENTO_LABELS,
    SITUACOES_COBRANCA,
    STATUSES_ACEITAM_PAGAMENTO,
    WORK_ORDER_STATUS_LABELS,
)
from app.schemas.clients import ClientOut
from app.schemas.common import Page
from app.schemas.vehicles import VehicleOut
from app.schemas.intake import IntakeIn
from app.schemas.payments import EstornoIn, PaymentIn, PaymentOut
from app.schemas.work_orders import (
    AgendaOut,
    AgendaResumoOut,
    EventOut,
    ItemIn,
    PatioOut,
    TransitionIn,
    TransitionOut,
    WorkOrderCreateIn,
    WorkOrderDetailOut,
    WorkOrderOut,
    WorkOrderUpdateIn,
)
from app.services import billing
from app.services import intake as intake_svc
from app.services import payments as pay_svc
from app.services import work_orders as svc
from app.services.periods import day_bounds, today_local

router = APIRouter(tags=["ordens de serviço"])


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except svc.WorkOrderError as e:
        raise HTTPException(e.status_code, e.detail) from e


def _pago(wo: WorkOrder) -> int:
    """Soma em Python sobre os pagamentos já carregados por `_base()` — nada de N+1 nas listas."""
    return sum(p.valor_centavos for p in wo.payments if p.estornado_em is None)


def _out(db, wo: WorkOrder, user) -> WorkOrderOut:
    """Monta a resposta com cliente, veículo e ações embutidos.

    As ações vêm aqui, e não só no detalhe, porque o cliente de celular desenha o botão de status
    no próprio card do pátio. `allowed_transitions` é Python puro sobre a OS já carregada — não
    custa consulta nenhuma a mais.
    """
    client = db.get(Client, wo.client_id)
    vehicle = db.get(Vehicle, wo.vehicle_id) if wo.vehicle_id else None
    pago = _pago(wo)
    # A MESMA regra que o filtro `?cobranca=` usa em SQL, aqui em Python sobre a OS já carregada.
    # tests/test_cobranca.py exige que as duas concordem em toda a matriz de casos.
    situacao = billing.situacao(
        status=wo.status,
        valor_total_centavos=wo.valor_total_centavos,
        pago_centavos=pago,
        vencimento=wo.vencimento,
        agora=datetime.now(timezone.utc),
    )
    return WorkOrderOut(
        id=wo.id,
        numero=wo.numero,
        previsao_manual=wo.previsao_manual,
        status=wo.status,
        status_label=WORK_ORDER_STATUS_LABELS.get(wo.status, wo.status),
        status_tone=svc.STATUS_TONES.get(wo.status, "neutral"),
        client_id=wo.client_id,
        vehicle_id=wo.vehicle_id,
        scheduled_at=wo.scheduled_at,
        entrada=wo.entrada,
        previsao_conclusao=wo.previsao_conclusao,
        conclusao=wo.conclusao,
        vencimento=wo.vencimento,
        desconto_centavos=wo.desconto_centavos,
        valor_total_centavos=wo.valor_total_centavos,
        pago_centavos=pago,
        saldo_centavos=max(0, wo.valor_total_centavos - pago),
        observacoes=wo.observacoes,
        observacoes_entrada=wo.observacoes_entrada,
        created_at=wo.created_at,
        updated_at=wo.updated_at,
        itens=wo.items,  # type: ignore[arg-type]
        cliente=ClientOut.model_validate(client),
        veiculo=VehicleOut.model_validate(vehicle) if vehicle else None,
        acoes=[TransitionOut(**t) for t in svc.allowed_transitions(wo, user)],
        aceita_pagamento=wo.status in STATUSES_ACEITAM_PAGAMENTO,
        situacao_cobranca=situacao,
        situacao_cobranca_label=billing.label(situacao),
        situacao_cobranca_tone=billing.tone(situacao),
    )


def _detail(db, wo: WorkOrder, user) -> WorkOrderDetailOut:
    base = _out(db, wo, user)
    return WorkOrderDetailOut(
        **base.model_dump(),
        eventos=[
            EventOut(
                id=e.id,
                tipo=e.tipo,
                descricao=svc.descreve_evento(e),
                de=e.de,
                para=e.para,
                motivo=e.motivo,
                user_id=e.user_id,
                created_at=e.created_at,
            )
            for e in wo.events
        ],
        pagamentos=[
            PaymentOut(
                id=p.id,
                valor_centavos=p.valor_centavos,
                forma=p.forma,
                forma_label=FORMAS_PAGAMENTO_LABELS.get(p.forma, p.forma),
                pago_em=p.pago_em,
                created_at=p.created_at,
                observacao=p.observacao,
                estornado_em=p.estornado_em,
                estorno_motivo=p.estorno_motivo,
                created_by=p.created_by,
                pode_estornar=pay_svc.pode_estornar(p, user),
            )
            for p in wo.payments
        ],
    )


def _get_or_404(db, work_order_id: int) -> WorkOrder:
    wo = svc.get_work_order(db, work_order_id)
    if wo is None:
        raise HTTPException(404, "Ordem de serviço não encontrada.")
    return wo


# ------------------------------------------------------------------ agenda


@router.get("/agenda", response_model=AgendaOut)
def agenda(db: DB, auth: Auth, dia: date | None = None) -> AgendaOut:
    """Agenda de um dia (fuso America/Maceio) com os contadores do cabeçalho."""
    alvo = dia or today_local()
    try:
        rows, resumo = svc.agenda_do_dia(db, alvo)
    except ValueError as e:  # data fora do calendário do sistema
        raise HTTPException(422, str(e)) from e
    return AgendaOut(
        dia=alvo.isoformat(),
        resumo=AgendaResumoOut(**resumo),
        itens=[_out(db, w, auth.user) for w in rows],
    )


@router.get("/patio", response_model=PatioOut)
def patio(db: DB, auth: Auth) -> PatioOut:
    """Carros que estão na loja agora, agrupados por status."""
    grupos = intake_svc.patio(db)
    return PatioOut(**{s: [_out(db, w, auth.user) for w in lista] for s, lista in grupos.items()})


@router.post("/work-orders/intake", response_model=WorkOrderDetailOut, status_code=201)
def receber_veiculo(body: IntakeIn, db: DB, auth: Auth) -> WorkOrderDetailOut:
    """Recepção: cria o que faltar (cliente, veículo) e abre a OS recebida — tudo numa transação."""
    wo = _run(intake_svc.receber, db, body.model_dump(), user=auth.user)
    return _detail(db, wo, auth.user)


# ------------------------------------------------------------------ ordens de serviço


@router.get("/work-orders", response_model=Page[WorkOrderOut])
def list_work_orders(
    db: DB,
    auth: Auth,
    status: list[str] | None = Query(None),
    de: date | None = None,
    ate: date | None = None,
    client_id: int | None = None,
    vehicle_id: int | None = None,
    q: str | None = Query(None, max_length=120),
    cobranca: str | None = Query(None, description="pendente | atrasado | pago"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Page[WorkOrderOut]:
    try:
        de_dt: datetime | None = day_bounds(de)[0] if de else None
        ate_dt: datetime | None = day_bounds(ate)[1] if ate else None
    except ValueError as e:  # data fora do calendário do sistema
        raise HTTPException(422, str(e)) from e
    if cobranca is not None and cobranca not in SITUACOES_COBRANCA:
        raise HTTPException(422, "Situação de cobrança inválida.")
    rows, total = svc.list_work_orders(
        db,
        status=status,
        de=de_dt,
        ate=ate_dt,
        client_id=client_id,
        vehicle_id=vehicle_id,
        q=q,
        cobranca=cobranca,
        page=page,
        page_size=page_size,
    )
    return Page(items=[_out(db, w, auth.user) for w in rows], total=total, page=page, page_size=page_size)


@router.post("/work-orders", response_model=WorkOrderDetailOut, status_code=201)
def create_work_order(body: WorkOrderCreateIn, db: DB, auth: Auth) -> WorkOrderDetailOut:
    wo = _run(svc.create_work_order, db, body.model_dump(), user=auth.user)
    return _detail(db, wo, auth.user)


@router.get("/work-orders/{work_order_id}", response_model=WorkOrderDetailOut)
def get_work_order(work_order_id: int, db: DB, auth: Auth) -> WorkOrderDetailOut:
    return _detail(db, _get_or_404(db, work_order_id), auth.user)


@router.patch("/work-orders/{work_order_id}", response_model=WorkOrderDetailOut)
def update_work_order(work_order_id: int, body: WorkOrderUpdateIn, db: DB, auth: Auth) -> WorkOrderDetailOut:
    wo = _run(svc.update_work_order, db, work_order_id, body.model_dump(exclude_unset=True), user=auth.user)
    return _detail(db, wo, auth.user)


@router.post("/work-orders/{work_order_id}/payments", response_model=WorkOrderDetailOut, status_code=201)
def registrar_pagamento(work_order_id: int, body: PaymentIn, db: DB, auth: Auth) -> WorkOrderDetailOut:
    """Lança um pagamento. Uma forma por lançamento: Pix + dinheiro são dois."""
    wo = _run(pay_svc.registrar, db, work_order_id, body.model_dump(), user=auth.user)
    return _detail(db, wo, auth.user)


@router.post("/work-orders/{work_order_id}/payments/{payment_id}/estorno", response_model=WorkOrderDetailOut)
def estornar_pagamento(
    work_order_id: int, payment_id: int, body: EstornoIn, db: DB, auth: Auth
) -> WorkOrderDetailOut:
    """Desfaz um lançamento sem apagá-lo. Quem lançou desfaz o próprio; o resto é do administrador."""
    wo = _run(pay_svc.estornar, db, work_order_id, payment_id, motivo=body.motivo, user=auth.user)
    return _detail(db, wo, auth.user)


@router.post("/work-orders/{work_order_id}/transition", response_model=WorkOrderDetailOut)
def transition(work_order_id: int, body: TransitionIn, db: DB, auth: Auth) -> WorkOrderDetailOut:
    wo = _run(
        svc.change_status,
        db,
        work_order_id,
        to_status=body.to_status,
        expected_status=body.expected_status,
        motivo=body.motivo,
        user=auth.user,
    )
    return _detail(db, wo, auth.user)


@router.post("/work-orders/{work_order_id}/items", response_model=WorkOrderDetailOut)
def add_items(work_order_id: int, body: list[ItemIn], db: DB, auth: Auth) -> WorkOrderDetailOut:
    wo = _run(svc.add_items, db, work_order_id, [i.model_dump() for i in body], user=auth.user)
    return _detail(db, wo, auth.user)


@router.delete("/work-orders/{work_order_id}/items/{item_id}", response_model=WorkOrderDetailOut)
def remove_item(work_order_id: int, item_id: int, db: DB, auth: Auth) -> WorkOrderDetailOut:
    wo = _run(svc.remove_item, db, work_order_id, item_id, user=auth.user)
    return _detail(db, wo, auth.user)


@router.delete("/work-orders/{work_order_id}", status_code=204)
def delete_work_order(work_order_id: int, db: DB, _admin: AdminUser) -> None:
    _run(svc.delete_work_order, db, work_order_id)
