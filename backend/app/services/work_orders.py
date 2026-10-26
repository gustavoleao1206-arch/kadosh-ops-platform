"""Ordens de serviço: orçamento, agenda e pátio — uma entidade só.

Regras centrais (todas aqui, nunca nos clientes):
- Máquina de estados: TRANSITIONS diz o que é permitido; a rota só desenha os botões que a API devolve.
- Total: `recalc_total` é a ÚNICA função que escreve `valor_total_centavos`, sempre com lock da OS.
- Todo evento (status, item, desconto) grava `work_order_events` na MESMA transação.
- Fronteira de transação: funções públicas comitam; helpers com prefixo `_` só fazem flush.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Client,
    Payment,
    Service,
    User,
    Vehicle,
    WorkOrder,
    WorkOrderEvent,
    WorkOrderItem,
    work_order_numero_seq,
)
from app.models.enums import (
    FORMAS_PAGAMENTO_LABELS,
    STATUSES_ACEITAM_PAGAMENTO,
    STATUSES_NO_PATIO,
    STATUSES_SEM_VEICULO,
    STATUSES_TERMINAIS,
    WORK_ORDER_STATUS_LABELS,
    WORK_ORDER_STATUSES,
)
from app.services import billing
from app.services import pricing
from app.services.periods import day_bounds, to_local, today_local

# Para onde cada status pode ir. Saltos para frente e um passo atrás são permitidos de propósito:
# ninguém volta ao celular para apertar "iniciar execução" numa lavagem rápida.
TRANSITIONS: dict[str, set[str]] = {
    "orcamento": {"agendado", "recebido", "cancelado"},
    "agendado": {"confirmado", "recebido", "cancelado", "nao_compareceu"},
    "confirmado": {"agendado", "recebido", "cancelado", "nao_compareceu"},
    "recebido": {"em_execucao", "aguardando_retirada", "concluido", "cancelado"},
    "em_execucao": {"recebido", "aguardando_retirada", "concluido", "cancelado"},
    "aguardando_retirada": {"em_execucao", "concluido", "cancelado"},
    "concluido": {"aguardando_retirada"},  # reabertura: só admin
    "cancelado": set(),
    "nao_compareceu": {"agendado"},  # remarcar
}

# Transições que só o administrador pode fazer.
ADMIN_ONLY: set[tuple[str, str]] = {("concluido", "aguardando_retirada")}

# Transições que exigem justificativa.
REQUIRE_MOTIVO = {"cancelado", "nao_compareceu"}

# O que o BOTÃO diz (verbo), diferente do rótulo do estado. "Confirmado" é estado; "Confirmar" é ação.
ACTION_LABELS = {
    "orcamento": "Voltar para orçamento",
    "agendado": "Agendar",
    "confirmado": "Confirmar",
    "recebido": "Receber veículo",
    "em_execucao": "Iniciar execução",
    "aguardando_retirada": "Marcar como pronto",
    "concluido": "Concluir e entregar",
    "cancelado": "Cancelar",
    "nao_compareceu": "Não compareceu",
}

# O passo natural a partir de cada status: vira o botão em destaque no balcão e no celular.
PROXIMO_PASSO = {
    "orcamento": "agendado",
    "agendado": "recebido",
    "confirmado": "recebido",
    "recebido": "em_execucao",
    "em_execucao": "aguardando_retirada",
    "aguardando_retirada": "concluido",
    "nao_compareceu": "agendado",
}

# Voltar um passo não é a mesma ação que avançar até ele: "receber" de novo um carro que já está
# no pátio não quer dizer nada. Aqui o botão ganha o verbo certo para o caminho de volta.
ACTION_LABELS_VOLTA = {
    ("em_execucao", "recebido"): "Voltar para a fila",
    ("aguardando_retirada", "em_execucao"): "Voltar para execução",
    ("confirmado", "agendado"): "Desfazer confirmação",
    ("concluido", "aguardando_retirada"): "Reabrir OS",
    ("nao_compareceu", "agendado"): "Remarcar",
}

# Cor de cada status para os dois clientes (fonte única).
STATUS_TONES = {
    "orcamento": "neutral",
    "agendado": "gold",
    "confirmado": "gold",
    "recebido": "warn",
    "em_execucao": "warn",
    "aguardando_retirada": "ok",
    "concluido": "ok",
    "cancelado": "danger",
    "nao_compareceu": "danger",
}

STATUSES_AGENDA = ("agendado", "confirmado")

# Encerradas de verdade: nem data nem serviços mudam. "nao_compareceu" fica de fora porque
# remarcar exige definir a nova data antes de voltar para "agendado".
STATUSES_FECHADOS = ("cancelado", "concluido")
# Serviços e desconto congelam também em "nao_compareceu" (nada a executar).
STATUSES_SEM_ITENS = ("cancelado", "concluido", "nao_compareceu")

# A única coisa que ainda se edita numa OS CONCLUÍDA. O carro entregue devendo é justamente a OS
# que precisa ganhar um prazo — travar tudo depois da entrega deixaria a cobrança sem data para
# sempre, e a régua de atraso sem como distinguir "combinamos para sexta" de "sumiu com o carro".
CAMPOS_POS_CONCLUSAO = {"vencimento"}


class WorkOrderError(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def reais(centavos: int) -> str:
    """12345 -> "R$ 123,45". Só para texto que o balcão lê; o payload continua em centavos."""
    return f"R$ {centavos / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


# --------------------------------------------------------------------------- consultas


def _base():
    return (
        select(WorkOrder)
        .options(
            selectinload(WorkOrder.items),
            selectinload(WorkOrder.events),
            selectinload(WorkOrder.payments),
        )
        .execution_options(populate_existing=True)
    )


def get_work_order(db: Session, work_order_id: int) -> WorkOrder | None:
    return db.scalar(_base().where(WorkOrder.id == work_order_id))


def get_locked(db: Session, work_order_id: int) -> WorkOrder:
    """Carrega a OS com lock da linha — usado por toda mutação que mexe em valores.

    `populate_existing` é obrigatório: sem ele o SELECT ... FOR UPDATE devolve a instância que já
    estava na sessão (com os valores lidos ANTES do lock) e as regras validariam dados velhos.
    """
    wo = db.scalar(
        select(WorkOrder)
        .where(WorkOrder.id == work_order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if wo is None:
        raise WorkOrderError("Ordem de serviço não encontrada.", 404)
    return wo


def list_work_orders(
    db: Session,
    *,
    status: list[str] | None,
    de: datetime | None,
    ate: datetime | None,
    client_id: int | None,
    vehicle_id: int | None,
    q: str | None,
    cobranca: str | None,
    page: int,
    page_size: int,
) -> tuple[list[WorkOrder], int]:
    stmt = _base()
    if status:
        stmt = stmt.where(WorkOrder.status.in_(status))
    if cobranca:
        # O filtro roda em SQL porque a paginação precisa: peneirar em Python devolveria "página 1
        # de 50" com 6 linhas. A conta é a de billing.situacao_sql — a mesma que a tela mostra.
        pago = billing.pago_por_os()
        stmt = stmt.outerjoin(pago, pago.c.wid == WorkOrder.id).where(
            billing.situacao_sql(pago.c.pago, agora=_now()) == cobranca
        )
    if client_id is not None:
        stmt = stmt.where(WorkOrder.client_id == client_id)
    if vehicle_id is not None:
        stmt = stmt.where(WorkOrder.vehicle_id == vehicle_id)
    # a data que importa: a marcada (agenda) ou a de entrada (pátio)
    quando = func.coalesce(WorkOrder.scheduled_at, WorkOrder.entrada, WorkOrder.created_at)
    if de is not None:
        stmt = stmt.where(quando >= de)
    if ate is not None:
        stmt = stmt.where(quando < ate)
    if q:
        like = f"%{q.strip()}%"
        stmt = (
            stmt.join(Client, Client.id == WorkOrder.client_id)
            .outerjoin(Vehicle, Vehicle.id == WorkOrder.vehicle_id)
            .where(
                or_(
                    func.unaccent(func.lower(Client.nome)).ilike(func.unaccent(func.lower(like))),
                    Vehicle.placa.contains(q.strip().upper().replace("-", "")),
                    func.unaccent(func.lower(Vehicle.modelo)).ilike(func.unaccent(func.lower(like))),
                )
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.order_by(quando.desc(), WorkOrder.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return rows, total


def _no_dia(ini: datetime, fim: datetime):
    """O predicado de "aparece na agenda deste dia" — usado pela agenda e pelos contadores."""
    return or_(
        and_(WorkOrder.scheduled_at >= ini, WorkOrder.scheduled_at < fim),
        and_(WorkOrder.entrada >= ini, WorkOrder.entrada < fim),
        # carro que ainda está no pátio aparece todo dia, até sair
        and_(WorkOrder.status.in_(STATUSES_NO_PATIO), WorkOrder.entrada < fim),
    )


def contadores_do_dia(db: Session, dia=None) -> dict:
    """Só os quatro números do cabeçalho, sem carregar OS nenhuma.

    Existe para o dashboard: a home do celular abre muitas vezes por dia, e pedir `agenda_do_dia`
    só para contar significava hidratar cada OS do dia com itens, eventos e pagamentos — três
    consultas extras e um punhado de objetos, para no fim usar quatro inteiros.
    """
    dia = dia or today_local()
    ini, fim = day_bounds(dia)
    no_dia = _no_dia(ini, fim)

    def quantas(*filtros) -> int:
        return int(db.scalar(select(func.count()).select_from(WorkOrder).where(*filtros)) or 0)

    return {
        "agendados": quantas(no_dia, WorkOrder.status == "agendado"),
        "confirmados": quantas(no_dia, WorkOrder.status == "confirmado"),
        "no_patio": quantas(WorkOrder.status.in_(STATUSES_NO_PATIO)),
        "orcamentos_abertos": quantas(WorkOrder.status == "orcamento"),
    }


def agenda_do_dia(db: Session, dia=None) -> tuple[list[WorkOrder], dict]:
    """Agendamentos do dia (fuso local) + contadores usados no cabeçalho da agenda."""
    dia = dia or today_local()
    ini, fim = day_bounds(dia)
    rows = db.scalars(
        _base()
        .where(_no_dia(ini, fim), WorkOrder.status != "orcamento")
        .order_by(func.coalesce(WorkOrder.scheduled_at, WorkOrder.entrada), WorkOrder.id)
    ).all()
    return rows, contadores_do_dia(db, dia)


# --------------------------------------------------------------------------- helpers (sem commit)


def _event(db: Session, wo: WorkOrder, *, tipo: str, de=None, para=None, motivo=None, user: User | None) -> None:
    db.add(
        WorkOrderEvent(
            work_order_id=wo.id, tipo=tipo, de=de, para=para, motivo=motivo, user_id=user.id if user else None
        )
    )


def pago_centavos(db: Session, wo: WorkOrder) -> int:
    """Quanto já entrou nesta OS (pagamentos não estornados)."""
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Payment.valor_centavos), 0)).where(
                Payment.work_order_id == wo.id, Payment.estornado_em.is_(None)
            )
        )
        or 0
    )


def saldo_em_aberto(db: Session, wo: WorkOrder) -> int:
    """Quanto falta receber nesta OS. Nunca negativo — o piso de `recalc_total` garante."""
    return max(0, wo.valor_total_centavos - pago_centavos(db, wo))


def recalc_total(db: Session, wo: WorkOrder) -> None:
    """Única escrita de valor_total_centavos. A OS já deve estar travada (get_locked)."""
    soma = db.scalar(
        select(func.coalesce(func.sum(WorkOrderItem.valor_centavos), 0)).where(WorkOrderItem.work_order_id == wo.id)
    ) or 0
    if wo.desconto_centavos > soma:
        raise WorkOrderError("O desconto não pode ser maior que a soma dos serviços.", 422)
    total = int(soma) - wo.desconto_centavos
    # Piso: o total nunca fica abaixo do que já foi recebido, senão o saldo vira negativo e ninguém
    # sabe ler "a receber −R$ 50" no balcão. Desconto, remoção de item e reabertura passam todos por
    # aqui, então uma checagem só cobre os cinco caminhos.
    if wo.id is not None:
        pago = pago_centavos(db, wo)
        if total < pago:
            raise WorkOrderError(
                f"Esta OS já recebeu {reais(pago)}. Estorne um pagamento antes de reduzir o total "
                f"para {reais(total)}.",
                409,
            )
    wo.valor_total_centavos = total
    db.flush()


def _duracao_total_min(db: Session, wo: WorkOrder) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Service.duracao_estimada_min), 0))
            .select_from(WorkOrderItem)
            .join(Service, Service.id == WorkOrderItem.service_id)
            .where(WorkOrderItem.work_order_id == wo.id)
        )
        or 0
    )


def _refresh_previsao(db: Session, wo: WorkOrder) -> None:
    """Previsão = base (entrada ou horário marcado) + soma das durações. Não mexe se foi definida à mão."""
    if wo.previsao_manual:
        return
    base = wo.entrada or wo.scheduled_at
    minutos = _duracao_total_min(db, wo)
    # sem serviço lançado não há o que estimar: prever "agora" faria o carro nascer atrasado
    wo.previsao_conclusao = base + timedelta(minutes=minutos) if base is not None and minutos > 0 else None
    db.flush()


def _add_items(db: Session, wo: WorkOrder, itens: list[dict], *, user: User | None) -> None:
    """Copia nome e valor do catálogo no momento do lançamento (o histórico não muda depois).

    Item que chega com uma chave já usada nesta OS é ignorado: é o mesmo toque chegando de novo.
    Sem isso, tocar duas vezes em "lançar" numa rede ruim dobra o total da OS. Chave de OUTRA OS é
    409, como no pagamento — engolir em silêncio devolveria 200 com o serviço faltando, e ninguém
    olharia de novo.
    """
    # uma consulta só para a OS inteira: perguntar o preço item a item seria N+1 no lançamento
    combinados = pricing.precos_do_cliente(db, wo.client_id) if itens else {}
    for item in itens:
        chave = item.get("idempotency_key")
        if chave:
            repetido = db.scalar(select(WorkOrderItem).where(WorkOrderItem.idempotency_key == chave))
            if repetido is not None:
                if repetido.work_order_id != wo.id:
                    raise WorkOrderError("Este lançamento pertence a outra OS. Recarregue a tela.", 409)
                continue
        service = db.get(Service, item["service_id"])
        if service is None:
            raise WorkOrderError(f"Serviço {item['service_id']} não encontrado.", 404)
        if not service.ativo and item.get("valor_centavos") is None:
            raise WorkOrderError(f"O serviço “{service.nome}” está desativado.", 409)
        # A cadeia: digitado na hora > preço combinado com este cliente > tabela. O que sair daqui
        # é COPIADO para o item e nunca mais muda — mexer no combinado amanhã não reescreve esta OS.
        valor = item.get("valor_centavos")
        valor = pricing.valor_efetivo(service, combinados.get(service.id)) if valor is None else int(valor)
        if valor < 0:
            raise WorkOrderError("Valor do serviço não pode ser negativo.", 422)
        db.add(
            WorkOrderItem(
                work_order_id=wo.id,
                service_id=service.id,
                descricao=service.nome,
                valor_centavos=valor,
                idempotency_key=chave,
            )
        )
        _event(db, wo, tipo="item", para=f"+ {service.nome}", user=user)
    db.flush()


# Status que provam que o serviço saiu do papel — se a OS já passou por um deles, o laudo de
# entrada está congelado para o staff, mesmo que agora ela esteja de volta em "recebido".
STATUSES_EXECUCAO = ("em_execucao", "aguardando_retirada", "concluido")


def _ja_comecou(db: Session, wo: WorkOrder) -> bool:
    return db.scalar(
        select(func.count())
        .select_from(WorkOrderEvent)
        .where(
            WorkOrderEvent.work_order_id == wo.id,
            WorkOrderEvent.tipo == "status",
            WorkOrderEvent.para.in_(STATUSES_EXECUCAO),
        )
    ) > 0


def _validate_status_data(wo: WorkOrder) -> None:
    # Cancelar não precisa de carro: um orçamento recusado nunca teve um, e ficar sem saída
    # deixaria a OS presa para sempre.
    if wo.status not in STATUSES_SEM_VEICULO and wo.vehicle_id is None:
        raise WorkOrderError("Informe o veículo para agendar ou receber.", 422)
    if wo.status in STATUSES_AGENDA and wo.scheduled_at is None:
        raise WorkOrderError("Informe a data e a hora do agendamento.", 422)


# --------------------------------------------------------------------------- transições


def descreve_evento(ev: WorkOrderEvent) -> str:
    """Uma frase em português para a linha do histórico — os dois clientes só exibem."""
    label = lambda v: WORK_ORDER_STATUS_LABELS.get(v or "", v or "")  # noqa: E731
    if ev.tipo == "status":
        texto = f"{label(ev.de)} → {label(ev.para)}" if ev.de else f"Criada como {label(ev.para)}"
    elif ev.tipo == "item":
        texto = f"Serviço adicionado: {(ev.para or '').lstrip('+ ')}" if ev.para else f"Serviço removido: {(ev.de or '').lstrip('− ')}"
    elif ev.tipo == "remarcacao":
        def fmt(v):
            if not v:
                return "sem data"
            return to_local(datetime.fromisoformat(v)).strftime("%d/%m/%Y %H:%M")

        texto = f"Remarcado: {fmt(ev.de)} → {fmt(ev.para)}"
    elif ev.tipo == "reabertura":
        texto = "OS reaberta (conclusão desfeita)"
    elif ev.tipo == "transferencia":
        texto = "Veículo da OS trocado"
    elif ev.tipo == "entrada":
        texto = "Estado do carro na chegada alterado" if ev.para == "alterado" else "Estado do carro na chegada registrado"
    elif ev.tipo == "pagamento":
        # "pix 15000" — parse defensivo: uma linha estranha não pode derrubar o histórico inteiro
        bruto = ev.para or ev.de or ""
        forma, _, valor = bruto.partition(" ")
        rotulo = FORMAS_PAGAMENTO_LABELS.get(forma, forma or "—")
        quanto = reais(int(valor)) if valor.isdigit() else "—"
        verbo = "recebido" if ev.para else "estornado"
        texto = f"Pagamento {verbo}: {quanto} em {rotulo}"
    elif ev.tipo == "desconto":
        texto = f"Desconto: {reais(int(ev.de or 0))} → {reais(int(ev.para or 0))}"
    elif ev.tipo == "vencimento":
        def data(v):
            if not v:
                return "sem prazo"
            return to_local(datetime.fromisoformat(v)).strftime("%d/%m/%Y")

        texto = f"Vencimento: {data(ev.de)} → {data(ev.para)}"
    else:
        texto = ev.tipo
    return f"{texto} — {ev.motivo}" if ev.motivo else texto


def _principal(status: str, destinos: list[str]) -> str | None:
    """Qual dos botões é o passo esperado agora — o único que vem em destaque.

    Se o passo natural não estiver disponível (falta data, falta veículo), cai no próximo
    destino que ainda leva a OS para frente. Encerramentos nunca ganham destaque.
    """
    preferido = PROXIMO_PASSO.get(status)
    if preferido in destinos:
        return preferido
    atual = WORK_ORDER_STATUSES.index(status)
    for destino in destinos:
        if destino not in STATUSES_TERMINAIS and WORK_ORDER_STATUSES.index(destino) > atual:
            return destino
    return None


def allowed_transitions(wo: WorkOrder, user: User) -> list[dict]:
    """O que esta OS pode virar agora, para este usuário — com rótulo, cor e destaque em português."""
    destinos = []
    # na ordem do fluxo (WORK_ORDER_STATUSES), não em ordem alfabética: quem opera lê da esquerda
    # para a direita e espera "iniciar" antes de "concluir".
    for destino in WORK_ORDER_STATUSES:
        if destino not in TRANSITIONS.get(wo.status, set()):
            continue
        if (wo.status, destino) in ADMIN_ONLY and not user.is_admin:
            continue
        # botão que só levaria a 422: orçamento sem veículo não recebe, sem data não agenda.
        # Encerrar (cancelar / não compareceu) continua sempre disponível.
        if wo.vehicle_id is None and destino not in STATUSES_SEM_VEICULO:
            continue
        if destino in STATUSES_AGENDA and wo.scheduled_at is None:
            continue
        destinos.append(destino)

    principal = _principal(wo.status, destinos)
    return [
        {
            "status": destino,
            "label": WORK_ORDER_STATUS_LABELS[destino],
            "acao_label": ACTION_LABELS_VOLTA.get((wo.status, destino), ACTION_LABELS[destino]),
            "tone": STATUS_TONES[destino],
            "requer_motivo": destino in REQUIRE_MOTIVO or (wo.status, destino) in ADMIN_ONLY,
            "principal": destino == principal,
        }
        for destino in destinos
    ]


def change_status(
    db: Session,
    work_order_id: int,
    *,
    to_status: str,
    expected_status: str | None,
    motivo: str | None,
    user: User,
) -> WorkOrder:
    wo = get_locked(db, work_order_id)

    if expected_status and wo.status != expected_status:
        raise WorkOrderError(
            f"Esta OS mudou para “{WORK_ORDER_STATUS_LABELS.get(wo.status, wo.status)}” em outro aparelho. "
            "Recarregue para ver o estado atual.",
            409,
        )
    if to_status not in WORK_ORDER_STATUSES:
        raise WorkOrderError("Status inválido.", 422)
    if to_status == wo.status:
        raise WorkOrderError("A OS já está neste status.", 400)
    if to_status not in TRANSITIONS.get(wo.status, set()):
        raise WorkOrderError(
            f"Não é possível ir de “{WORK_ORDER_STATUS_LABELS[wo.status]}” para “{WORK_ORDER_STATUS_LABELS[to_status]}”.",
            409,
        )
    if (wo.status, to_status) in ADMIN_ONLY and not user.is_admin:
        raise WorkOrderError("Apenas o administrador pode reabrir uma OS concluída.", 403)
    if to_status in REQUIRE_MOTIVO and not (motivo or "").strip():
        raise WorkOrderError("Informe o motivo.", 422)
    if (wo.status, to_status) in ADMIN_ONLY and not (motivo or "").strip():
        raise WorkOrderError("Informe o motivo da reabertura.", 422)

    de = wo.status
    wo.status = to_status

    if to_status == "agendado" and de == "nao_compareceu":
        if wo.scheduled_at is None or wo.scheduled_at <= _now():
            raise WorkOrderError("Defina a nova data e hora antes de remarcar.", 422)

    # valida ANTES de tocar em entrada/numero: nextval nao volta atras e deixaria buraco na numeracao
    _validate_status_data(wo)

    if to_status == "recebido":
        if wo.entrada is None:
            wo.entrada = _now()
        if wo.numero is None:  # o número só existe a partir da recepção
            wo.numero = db.scalar(work_order_numero_seq.next_value())
    if to_status == "concluido":
        wo.conclusao = _now()
    if de == "concluido":  # reabertura: guarda o que está sendo apagado, antes de apagar
        _event(
            db,
            wo,
            tipo="reabertura",
            de=wo.conclusao.isoformat() if wo.conclusao else None,
            para=str(wo.valor_total_centavos),
            motivo=motivo,
            user=user,
        )
        wo.conclusao = None
    _refresh_previsao(db, wo)
    _event(db, wo, tipo="status", de=de, para=to_status, motivo=motivo, user=user)
    db.commit()
    return get_work_order(db, work_order_id)  # type: ignore[return-value]


# --------------------------------------------------------------------------- criação e edição


def create_work_order(db: Session, data: dict, *, user: User) -> WorkOrder:
    """Cria orçamento (sem veículo/data) ou agendamento (com veículo e data)."""
    status = data.get("status") or ("agendado" if data.get("scheduled_at") else "orcamento")
    if status not in ("orcamento", "agendado"):
        raise WorkOrderError("Uma OS nova nasce como orçamento ou agendamento.", 422)

    client = db.get(Client, data["client_id"])
    if client is None:
        raise WorkOrderError("Cliente não encontrado.", 404)
    if client.arquivado_em is not None:
        raise WorkOrderError("Este cliente está arquivado. Desarquive-o antes.", 409)

    vehicle_id = data.get("vehicle_id")
    if vehicle_id is not None:
        vehicle = db.get(Vehicle, vehicle_id)
        if vehicle is None:
            raise WorkOrderError("Veículo não encontrado.", 404)
        if vehicle.client_id != client.id:
            raise WorkOrderError("Este veículo não pertence ao cliente informado.", 422)
        if vehicle.arquivado_em is not None:
            raise WorkOrderError("Este veículo está arquivado. Desarquive-o antes.", 409)

    wo = WorkOrder(
        client_id=client.id,
        vehicle_id=vehicle_id,
        status=status,
        scheduled_at=data.get("scheduled_at"),
        desconto_centavos=int(data.get("desconto_centavos") or 0),
        observacoes=data.get("observacoes"),
        created_by=user.id,
    )
    db.add(wo)
    db.flush()
    _validate_status_data(wo)

    _add_items(db, wo, data.get("itens") or [], user=user)
    recalc_total(db, wo)
    _refresh_previsao(db, wo)
    _event(db, wo, tipo="status", de=None, para=status, user=user)
    db.commit()
    return get_work_order(db, wo.id)  # type: ignore[return-value]


def update_work_order(db: Session, work_order_id: int, data: dict, *, user: User) -> WorkOrder:
    """Data marcada, observações e desconto. Itens têm endpoints próprios."""
    wo = get_locked(db, work_order_id)
    if wo.status in STATUSES_FECHADOS and (
        wo.status != "concluido" or set(data) - CAMPOS_POS_CONCLUSAO
    ):
        raise WorkOrderError("Esta OS está encerrada e não pode mais ser editada.", 409)

    if "scheduled_at" in data and data["scheduled_at"] != wo.scheduled_at:
        antes = wo.scheduled_at
        wo.scheduled_at = data["scheduled_at"]
        _event(
            db,
            wo,
            tipo="remarcacao",
            de=antes.isoformat() if antes else None,
            para=wo.scheduled_at.isoformat() if wo.scheduled_at else None,
            user=user,
        )
        if wo.status == "confirmado":
            # a confirmação valia para a data antiga
            _event(db, wo, tipo="status", de="confirmado", para="agendado", motivo="Remarcado — confirmar de novo", user=user)
            wo.status = "agendado"
    if "observacoes" in data:
        wo.observacoes = data["observacoes"]
    if "observacoes_entrada" in data and data["observacoes_entrada"] != wo.observacoes_entrada:
        # O estado do carro na chegada é prova em caso de reclamação: depois que o serviço começa,
        # só o administrador altera. Vale o HISTÓRICO, não o status atual — voltar a OS para
        # "recebido" e editar seria uma porta dos fundos para quem causou o risco.
        if _ja_comecou(db, wo) and not user.is_admin:
            raise WorkOrderError("O serviço já começou: só o administrador altera as observações de entrada.", 403)
        # o texto antigo vai em `motivo` (Text): `de`/`para` têm 120 caracteres e um laudo é longo
        antigo = wo.observacoes_entrada
        _event(
            db,
            wo,
            tipo="entrada",
            para="alterado" if antigo else "registrado",
            motivo=f"Antes: {antigo}" if antigo else None,
            user=user,
        )
        wo.observacoes_entrada = data["observacoes_entrada"]
    if "vehicle_id" in data and data["vehicle_id"] != wo.vehicle_id:
        vehicle = db.get(Vehicle, data["vehicle_id"]) if data["vehicle_id"] else None
        if data["vehicle_id"] and vehicle is None:
            raise WorkOrderError("Veículo não encontrado.", 404)
        if vehicle is not None and vehicle.client_id != wo.client_id:
            raise WorkOrderError("Este veículo não pertence ao cliente da OS.", 422)
        # Com o carro já no pátio, trocar o veículo desliga o laudo de entrada do carro certo —
        # a prova iria parar no histórico de outro. Quem chegou em outro carro é recebido pela
        # recepção; corrigir depois é só do administrador, e sempre com registro.
        if wo.entrada is not None and not user.is_admin:
            raise WorkOrderError("O carro já está no pátio: só o administrador troca o veículo da OS.", 403)
        _event(db, wo, tipo="transferencia", de=str(wo.vehicle_id or ""), para=str(data["vehicle_id"] or ""), user=user)
        wo.vehicle_id = data["vehicle_id"]
    if "previsao_conclusao" in data:
        wo.previsao_conclusao = data["previsao_conclusao"]
        wo.previsao_manual = data["previsao_conclusao"] is not None
    if "desconto_centavos" in data:
        novo = int(data["desconto_centavos"] or 0)
        if novo != wo.desconto_centavos:
            # O motivo é opcional, mas quando vem fica gravado no evento: "por que este cliente
            # levou R$ 40 de abatimento" é a pergunta que aparece três meses depois.
            _event(
                db,
                wo,
                tipo="desconto",
                de=str(wo.desconto_centavos),
                para=str(novo),
                motivo=(data.get("desconto_motivo") or None),
                user=user,
            )
            wo.desconto_centavos = novo
    if "vencimento" in data and data["vencimento"] != wo.vencimento:
        novo_venc = data["vencimento"]
        # Prazo só faz sentido onde há dívida. Numa OS que não recebe dinheiro (orçamento,
        # cancelada), a data seria enfeite que ainda por cima mente na régua.
        if novo_venc is not None and wo.status not in STATUSES_ACEITAM_PAGAMENTO:
            raise WorkOrderError("Esta OS ainda não recebe pagamento; não há prazo a definir.", 409)
        _event(
            db,
            wo,
            tipo="vencimento",
            de=wo.vencimento.isoformat() if wo.vencimento else None,
            para=novo_venc.isoformat() if novo_venc else None,
            user=user,
        )
        wo.vencimento = novo_venc

    _validate_status_data(wo)
    recalc_total(db, wo)
    # A checagem de saldo vem DEPOIS do recálculo, e não junto com a do status lá em cima, porque o
    # mesmo PATCH pode mexer no desconto: validar antes olharia um total que a própria requisição
    # está prestes a mudar. Tirar um desconto CRIA saldo (e o prazo passa a ser legítimo); pôr um
    # desconto pode QUITAR a OS (e aí o prazo tem de ser recusado). Como o raise desfaz a transação
    # inteira, nada da edição sobra pela metade.
    if wo.vencimento is not None and saldo_em_aberto(db, wo) <= 0:
        raise WorkOrderError("Esta OS não tem saldo a receber.", 409)
    _refresh_previsao(db, wo)
    db.commit()
    return get_work_order(db, work_order_id)  # type: ignore[return-value]


def add_items(db: Session, work_order_id: int, itens: list[dict], *, user: User) -> WorkOrder:
    wo = get_locked(db, work_order_id)
    if wo.status == "concluido":
        raise WorkOrderError("OS concluída: reabra antes de alterar os serviços.", 409)
    if wo.status in STATUSES_SEM_ITENS:
        raise WorkOrderError("Esta OS está encerrada e não pode mais ser editada.", 409)
    _add_items(db, wo, itens, user=user)
    recalc_total(db, wo)
    _refresh_previsao(db, wo)
    db.commit()
    return get_work_order(db, work_order_id)  # type: ignore[return-value]


def remove_item(db: Session, work_order_id: int, item_id: int, *, user: User) -> WorkOrder:
    wo = get_locked(db, work_order_id)
    if wo.status == "concluido":
        raise WorkOrderError("OS concluída: reabra antes de alterar os serviços.", 409)
    if wo.status in STATUSES_SEM_ITENS:
        raise WorkOrderError("Esta OS está encerrada e não pode mais ser editada.", 409)
    item = db.get(WorkOrderItem, item_id)
    if item is None or item.work_order_id != wo.id:
        raise WorkOrderError("Serviço não encontrado nesta OS.", 404)
    soma = int(
        db.scalar(
            select(func.coalesce(func.sum(WorkOrderItem.valor_centavos), 0)).where(WorkOrderItem.work_order_id == wo.id)
        )
        or 0
    )
    if wo.desconto_centavos > soma - item.valor_centavos:
        valor = f"{wo.desconto_centavos / 100:.2f}".replace(".", ",")
        raise WorkOrderError(f"Reduza o desconto (R$ {valor}) antes de remover este serviço.", 409)
    _event(db, wo, tipo="item", de=f"− {item.descricao}", user=user)
    db.delete(item)
    db.flush()
    recalc_total(db, wo)
    _refresh_previsao(db, wo)
    db.commit()
    return get_work_order(db, work_order_id)  # type: ignore[return-value]


def delete_work_order(db: Session, work_order_id: int) -> None:
    """Só admin e só OS sem número, isto é, orçamento ou agendamento (itens e eventos vão junto).

    Não há checagem de pagamento porque ela é inalcançável: dinheiro só entra a partir de
    "recebido" (STATUSES_ACEITAM_PAGAMENTO) e receber é justamente o que atribui o número. Se um dia
    o pagamento for liberado antes disso, esta regra cai junto — a FK RESTRICT de payments seria a
    única defesa, e com mensagem ruim.
    """
    wo = get_locked(db, work_order_id)
    if wo.numero is not None:
        raise WorkOrderError("Esta OS já foi recebida no pátio; cancele-a em vez de excluir.", 409)
    db.delete(wo)
    db.commit()
