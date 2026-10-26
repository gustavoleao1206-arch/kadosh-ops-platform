"""Veículos: cadastro, busca, arquivar, transferir de cliente. Uma função pública = uma transação."""

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.text import placa_fragment
from app.models import Client, Vehicle, WorkOrder
from app.models.enums import STATUSES_TERMINAIS


class VehicleError(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _base():
    # populate_existing: recarrega objetos já na sessão (ex.: relação `client` após transferência)
    return select(Vehicle).options(selectinload(Vehicle.client)).execution_options(populate_existing=True)


def get_vehicle(db: Session, vehicle_id: int) -> Vehicle | None:
    return db.scalar(_base().where(Vehicle.id == vehicle_id))


def open_work_orders(db: Session, *, vehicle_id: int | None = None, client_id: int | None = None) -> int:
    """OS não terminais (orçamento, agenda, pátio) ligadas ao veículo/cliente. Helper sem commit."""
    stmt = select(func.count()).select_from(WorkOrder).where(WorkOrder.status.not_in(STATUSES_TERMINAIS))
    if vehicle_id is not None:
        stmt = stmt.where(WorkOrder.vehicle_id == vehicle_id)
    if client_id is not None:
        stmt = stmt.where(WorkOrder.client_id == client_id)
    return db.scalar(stmt) or 0


def list_vehicles(
    db: Session, *, q: str | None, client_id: int | None, page: int, page_size: int, arquivados: bool
) -> tuple[list[Vehicle], int]:
    stmt = _base()
    stmt = stmt.where(Vehicle.arquivado_em.is_not(None) if arquivados else Vehicle.arquivado_em.is_(None))
    if client_id is not None:
        stmt = stmt.where(Vehicle.client_id == client_id)
    if q:
        like = f"%{q.strip()}%"
        conds = [
            func.unaccent(func.lower(Vehicle.modelo)).ilike(func.unaccent(func.lower(like))),
            func.unaccent(func.lower(Vehicle.marca)).ilike(func.unaccent(func.lower(like))),
        ]
        placa = placa_fragment(q)
        if placa:
            conds.append(Vehicle.placa.contains(placa))
        stmt = stmt.where(or_(*conds))
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.order_by(Vehicle.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return rows, total


def _check_active_plate(db: Session, placa: str | None, *, exclude_id: int | None = None) -> None:
    if not placa:
        return
    stmt = select(Vehicle).options(selectinload(Vehicle.client)).where(
        Vehicle.placa == placa, Vehicle.arquivado_em.is_(None)
    )
    if exclude_id is not None:
        stmt = stmt.where(Vehicle.id != exclude_id)
    other = db.scalar(stmt)
    if other:
        raise VehicleError(
            f"Já existe um veículo ativo com a placa {placa} ({other.client.nome}). "
            "Transfira-o para o novo dono ou arquive o antigo.",
            409,
        )


def _active_client(db: Session, client_id: int) -> Client:
    client = db.get(Client, client_id)
    if client is None:
        raise VehicleError("Cliente não encontrado.", 404)
    if client.arquivado_em is not None:
        raise VehicleError("Este cliente está arquivado. Desarquive-o antes.", 409)
    return client


def create_vehicle(db: Session, data: dict) -> Vehicle:
    _active_client(db, data["client_id"])
    _check_active_plate(db, data.get("placa"))
    vehicle = Vehicle(**data)
    db.add(vehicle)
    db.commit()
    return get_vehicle(db, vehicle.id)  # type: ignore[return-value]


def update_vehicle(db: Session, vehicle: Vehicle, data: dict, *, remover_placa: bool) -> Vehicle:
    if remover_placa:
        data["placa"] = None
    if "placa" in data and data["placa"] != vehicle.placa and vehicle.arquivado_em is None:
        _check_active_plate(db, data["placa"], exclude_id=vehicle.id)
    for field, value in data.items():
        setattr(vehicle, field, value)
    db.commit()
    return get_vehicle(db, vehicle.id)  # type: ignore[return-value]


def archive_vehicle(db: Session, vehicle: Vehicle) -> Vehicle:
    if vehicle.arquivado_em is not None:
        return vehicle
    if open_work_orders(db, vehicle_id=vehicle.id):
        raise VehicleError("Este veículo tem ordem de serviço em aberto; conclua ou cancele antes de arquivar.", 409)
    vehicle.arquivado_em = _now()
    db.commit()
    return get_vehicle(db, vehicle.id)  # type: ignore[return-value]


def unarchive_vehicle(db: Session, vehicle: Vehicle) -> Vehicle:
    _active_client(db, vehicle.client_id)
    _check_active_plate(db, vehicle.placa, exclude_id=vehicle.id)
    vehicle.arquivado_em = None
    db.commit()
    return get_vehicle(db, vehicle.id)  # type: ignore[return-value]


def transfer_vehicle(db: Session, vehicle: Vehicle, *, new_client_id: int) -> Vehicle:
    """Carro vendido: muda de dono sem perder histórico (as OS guardam o próprio client_id)."""
    if new_client_id == vehicle.client_id:
        raise VehicleError("O veículo já pertence a este cliente.", 400)
    _active_client(db, new_client_id)
    if open_work_orders(db, vehicle_id=vehicle.id):
        raise VehicleError("Este veículo tem ordem de serviço em aberto; conclua ou cancele antes de transferir.", 409)
    vehicle.client_id = new_client_id
    db.commit()
    return get_vehicle(db, vehicle.id)  # type: ignore[return-value]


def delete_vehicle(db: Session, vehicle: Vehicle) -> None:
    db.delete(vehicle)
    db.commit()
