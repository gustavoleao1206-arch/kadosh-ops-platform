"""Recepção do veículo: uma transação para cliente + veículo + OS.

Regra da fase: se qualquer passo falhar, NADA é criado. O balcão não pode ficar com um cliente
cadastrado sem carro nem com um carro sem OS porque a internet caiu no meio.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Client, User, Vehicle, WorkOrder, work_order_numero_seq
from app.services import work_orders as wo_service
from app.services.clients import find_by_phone
from app.services.work_orders import WorkOrderError, _add_items, _event, _now, _refresh_previsao, recalc_total


def _cliente(db: Session, dados: dict, *, user: User) -> Client:
    if dados.get("id"):
        client = db.get(Client, dados["id"])
        if client is None:
            raise WorkOrderError("Cliente não encontrado.", 404)
        if client.arquivado_em is not None:
            raise WorkOrderError("Este cliente está arquivado. Desarquive-o antes.", 409)
        return client

    telefone = dados.get("telefone")
    if telefone:
        # o mesmo telefone já cadastrado: usa o cliente existente em vez de duplicar
        existente = find_by_phone(db, telefone)
        if existente and existente.arquivado_em is None:
            return existente

    client = Client(nome=dados["nome"], telefone=telefone, email=dados.get("email"))
    db.add(client)
    db.flush()
    return client


def _veiculo(db: Session, dados: dict, client: Client) -> Vehicle:
    if dados.get("id"):
        vehicle = db.get(Vehicle, dados["id"])
        if vehicle is None:
            raise WorkOrderError("Veículo não encontrado.", 404)
        if vehicle.client_id != client.id:
            raise WorkOrderError("Este veículo não pertence ao cliente informado.", 422)
        if vehicle.arquivado_em is not None:
            raise WorkOrderError("Este veículo está arquivado. Desarquive-o antes.", 409)
        return vehicle

    placa = dados.get("placa")
    if placa:
        ativo = db.scalar(select(Vehicle).where(Vehicle.placa == placa, Vehicle.arquivado_em.is_(None)))
        if ativo is not None:
            if ativo.client_id != client.id:
                raise WorkOrderError(
                    f"A placa {placa} já está cadastrada para outro cliente. "
                    "Transfira o veículo para o novo dono antes de receber.",
                    409,
                )
            return ativo

    vehicle = Vehicle(
        client_id=client.id,
        placa=placa,
        marca=dados.get("marca"),
        modelo=dados["modelo"],
        cor=dados.get("cor"),
        ano=dados.get("ano"),
    )
    db.add(vehicle)
    db.flush()
    return vehicle


def _mesma_chave(db: Session, chave: str | None) -> WorkOrder | None:
    if not chave:
        return None
    ja_existe = db.scalar(select(WorkOrder).where(WorkOrder.idempotency_key == chave))
    return wo_service.get_work_order(db, ja_existe.id) if ja_existe is not None else None


def receber(db: Session, data: dict, *, user: User) -> WorkOrder:
    """Cria (ou reaproveita) cliente e veículo e abre a OS já recebida. Tudo ou nada."""
    chave = data.get("idempotency_key")
    # o toque repetido com sinal ruim devolve a mesma OS, não abre outra
    repetida = _mesma_chave(db, chave)
    if repetida is not None:
        return repetida

    try:
        return _receber(db, data, user=user, chave=chave)
    except IntegrityError:
        db.rollback()
        # corrida na chave de idempotência: a primeira requisição ganhou. O UNIQUE pode estourar
        # em qualquer flush depois da marcação, não só no commit — por isso o try cobre tudo.
        repetida = _mesma_chave(db, chave)
        if repetida is not None:
            return repetida
        raise


def _receber(db: Session, data: dict, *, user: User, chave: str | None) -> WorkOrder:
    # veio de um agendamento: recebe aquela OS em vez de criar outra
    if data.get("work_order_id") is not None:
        wo = wo_service.get_locked(db, data["work_order_id"])
        if wo.status not in ("orcamento", "agendado", "confirmado"):
            raise WorkOrderError("Esta OS já foi recebida.", 409)
        # o cliente é o da OS: mandar outro aqui não transfere nada, então nem é lido.
        if data.get("veiculo"):
            # chegou num carro diferente do que estava marcado
            client = db.get(Client, wo.client_id)
            wo.vehicle_id = _veiculo(db, data["veiculo"], client).id  # type: ignore[arg-type]
        elif wo.vehicle_id is None:
            raise WorkOrderError("Esta OS ainda não tem veículo. Informe qual carro chegou.", 422)
    else:
        client = _cliente(db, data["cliente"], user=user)
        vehicle = _veiculo(db, data["veiculo"], client)
        wo = WorkOrder(client_id=client.id, vehicle_id=vehicle.id, status="agendado", created_by=user.id)
        db.add(wo)
        db.flush()

    de = wo.status
    wo.status = "recebido"
    wo.entrada = wo.entrada or _now()
    wo.idempotency_key = chave
    if data.get("observacoes_entrada"):
        wo.observacoes_entrada = data["observacoes_entrada"]
    if data.get("observacoes"):
        wo.observacoes = data["observacoes"]
    if data.get("desconto_centavos"):
        wo.desconto_centavos = int(data["desconto_centavos"])

    _add_items(db, wo, data.get("itens") or [], user=user)
    recalc_total(db, wo)

    if data.get("previsao_conclusao"):
        wo.previsao_conclusao = data["previsao_conclusao"]
        wo.previsao_manual = True
    else:
        _refresh_previsao(db, wo)

    # O número só é tirado da sequence quando nada mais pode falhar: nextval não volta atrás no
    # rollback, e uma recepção recusada deixaria um buraco permanente na numeração.
    if wo.numero is None:
        wo.numero = db.scalar(work_order_numero_seq.next_value())

    _event(db, wo, tipo="status", de=de if data.get("work_order_id") else None, para="recebido", user=user)
    if data.get("observacoes_entrada"):
        _event(db, wo, tipo="entrada", para="registrado", user=user)
    db.commit()
    return wo_service.get_work_order(db, wo.id)  # type: ignore[return-value]


def patio(db: Session) -> dict[str, list[WorkOrder]]:
    """Carros que estão fisicamente na loja, agrupados por status — a visão do dia do sócio."""
    from app.models.enums import STATUSES_NO_PATIO

    rows = db.scalars(
        wo_service._base()
        .where(WorkOrder.status.in_(STATUSES_NO_PATIO))
        .order_by(WorkOrder.entrada)
    ).all()
    return {status: [w for w in rows if w.status == status] for status in STATUSES_NO_PATIO}
