"""Clientes: cadastro, busca, ficha com histórico, arquivar. Uma função pública = uma transação."""

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.text import only_digits
from app.models import Client, Vehicle, WorkOrder
from app.models.enums import WORK_ORDER_STATUS_LABELS
from app.schemas.clients import ClientStatsOut, WorkOrderSummaryOut
from app.services.vehicles import VehicleError, _check_active_plate, open_work_orders


class ClientError(Exception):
    def __init__(self, detail: str, status_code: int = 400, existing: Client | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.existing = existing


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _name_filter(q: str):
    like = f"%{q.strip()}%"
    return func.unaccent(func.lower(Client.nome)).ilike(func.unaccent(func.lower(like)))


def _ordered_by_name(stmt):
    # mesma normalização do filtro (collation C não ordena acentos); id desempata → paginação estável
    return stmt.order_by(func.unaccent(func.lower(Client.nome)), Client.id)


def list_clients(
    db: Session, *, q: str | None, page: int, page_size: int, arquivados: bool
) -> tuple[list[Client], int]:
    stmt = select(Client).options(selectinload(Client.vehicles))
    if arquivados:
        stmt = stmt.where(Client.arquivado_em.is_not(None))
    else:
        stmt = stmt.where(Client.arquivado_em.is_(None))
    if q:
        digits = only_digits(q)
        conds = [_name_filter(q)]
        if len(digits) >= 4:
            conds.append(Client.telefone.contains(digits))
        stmt = stmt.where(or_(*conds))
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(_ordered_by_name(stmt).offset((page - 1) * page_size).limit(page_size)).all()
    return rows, total


def get_client(db: Session, client_id: int) -> Client | None:
    return db.scalar(
        select(Client)
        .options(selectinload(Client.vehicles))
        .where(Client.id == client_id)
        .execution_options(populate_existing=True)  # recarrega `vehicles` mesmo se o objeto já está na sessão
    )


def find_by_phone(db: Session, telefone: str, *, exclude_id: int | None = None) -> Client | None:
    """Cliente com este telefone — ativos primeiro; arquivado também conta (a UI pode oferecer reativar)."""
    stmt = select(Client).options(selectinload(Client.vehicles)).where(Client.telefone == telefone)
    if exclude_id is not None:
        stmt = stmt.where(Client.id != exclude_id)
    return db.scalar(stmt.order_by(Client.arquivado_em.is_not(None), Client.id))


def create_client(
    db: Session, *, nome: str, telefone: str | None, email: str | None, observacoes: str | None, force: bool
) -> Client:
    """Telefone repetido avisa (409 com o cliente existente) — casal com um número usa force=true."""
    if telefone and not force:
        existing = find_by_phone(db, telefone)
        if existing:
            raise ClientError("Já existe um cliente com este telefone.", 409, existing=existing)
    client = Client(nome=nome, telefone=telefone, email=email, observacoes=observacoes)
    db.add(client)
    db.commit()
    return get_client(db, client.id)  # type: ignore[return-value]


def update_client(db: Session, client: Client, data: dict, *, force: bool = False) -> Client:
    tel = data.get("telefone")
    if tel and tel != client.telefone and not force:
        existing = find_by_phone(db, tel, exclude_id=client.id)
        if existing:
            raise ClientError("Já existe um cliente com este telefone.", 409, existing=existing)
    for field, value in data.items():
        setattr(client, field, value)
    db.commit()
    return get_client(db, client.id)  # type: ignore[return-value]


def archive_client(db: Session, client: Client) -> Client:
    """Arquiva o cliente e os veículos ativos dele com o MESMO carimbo (para o desarquivar desfazer)."""
    if client.arquivado_em is not None:
        return client  # idempotente: preserva o carimbo
    if open_work_orders(db, client_id=client.id):
        raise ClientError("Este cliente tem ordem de serviço em aberto; conclua ou cancele antes de arquivar.", 409)
    now = _now()
    client.arquivado_em = now
    for v in client.vehicles:
        if v.arquivado_em is None:
            v.arquivado_em = now
    db.commit()
    return get_client(db, client.id)  # type: ignore[return-value]


def unarchive_client(db: Session, client: Client) -> Client:
    """Reativa o cliente e os veículos que foram arquivados junto (placa em conflito fica arquivada)."""
    stamp = client.arquivado_em
    client.arquivado_em = None
    for v in client.vehicles:
        if stamp is not None and v.arquivado_em == stamp:
            try:
                _check_active_plate(db, v.placa, exclude_id=v.id)
            except VehicleError:
                continue
            v.arquivado_em = None
    db.commit()
    return get_client(db, client.id)  # type: ignore[return-value]


def delete_client(db: Session, client: Client) -> None:
    """Só admin e só sem histórico/veículos — caso contrário o banco responde com FK (409)."""
    db.delete(client)
    db.commit()


def client_stats(db: Session, client_id: int) -> ClientStatsOut:
    row = db.execute(
        select(
            func.count(WorkOrder.id),
            func.coalesce(func.sum(WorkOrder.valor_total_centavos), 0),
            func.max(WorkOrder.conclusao),
        ).where(WorkOrder.client_id == client_id, WorkOrder.status == "concluido")
    ).one()
    return ClientStatsOut(atendimentos=row[0], total_gasto_centavos=int(row[1]), ultimo_atendimento=row[2])


def work_order_history(
    db: Session, *, client_id: int | None = None, vehicle_id: int | None = None, limit: int = 50
) -> list[WorkOrderSummaryOut]:
    stmt = (
        select(WorkOrder, Vehicle, Client.nome)
        .join(Client, Client.id == WorkOrder.client_id)
        .outerjoin(Vehicle, Vehicle.id == WorkOrder.vehicle_id)
    )
    if client_id is not None:
        stmt = stmt.where(WorkOrder.client_id == client_id)
    if vehicle_id is not None:
        stmt = stmt.where(WorkOrder.vehicle_id == vehicle_id)
    rows = db.execute(
        stmt.order_by(
            func.coalesce(WorkOrder.entrada, WorkOrder.scheduled_at, WorkOrder.created_at).desc(), WorkOrder.id.desc()
        ).limit(limit)
    ).all()
    return [
        WorkOrderSummaryOut(
            id=wo.id,
            numero=wo.numero,
            status=wo.status,
            status_label=WORK_ORDER_STATUS_LABELS.get(wo.status, wo.status),
            scheduled_at=wo.scheduled_at,
            entrada=wo.entrada,
            conclusao=wo.conclusao,
            valor_total_centavos=wo.valor_total_centavos,
            vehicle_id=wo.vehicle_id,
            veiculo=veh.descricao if veh else None,
            client_id=wo.client_id,
            cliente=cliente_nome,
        )
        for wo, veh, cliente_nome in rows
    ]
