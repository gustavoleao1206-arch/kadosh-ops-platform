from fastapi import APIRouter, HTTPException, Query

from app.core.deps import DB, AdminUser, CurrentUser
from app.schemas.common import Page
from app.schemas.vehicles import VehicleCreateIn, VehicleDetailOut, VehicleOut, VehicleTransferIn, VehicleUpdateIn
from app.services import clients as clients_svc
from app.services import vehicles as svc

router = APIRouter(prefix="/vehicles", tags=["veículos"])


def _get_or_404(db, vehicle_id: int):
    vehicle = svc.get_vehicle(db, vehicle_id)
    if vehicle is None:
        raise HTTPException(404, "Veículo não encontrado.")
    return vehicle


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except svc.VehicleError as e:
        raise HTTPException(e.status_code, e.detail) from e


@router.get("", response_model=Page[VehicleOut])
def list_vehicles(
    db: DB,
    _user: CurrentUser,
    q: str | None = Query(None, max_length=120),
    client_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    arquivados: bool = False,
) -> Page[VehicleOut]:
    rows, total = svc.list_vehicles(
        db, q=q, client_id=client_id, page=page, page_size=page_size, arquivados=arquivados
    )
    return Page(items=[VehicleOut.model_validate(v) for v in rows], total=total, page=page, page_size=page_size)


@router.post("", response_model=VehicleOut, status_code=201)
def create_vehicle(body: VehicleCreateIn, db: DB, _user: CurrentUser) -> VehicleOut:
    return VehicleOut.model_validate(_run(svc.create_vehicle, db, body.model_dump()))


@router.get("/{vehicle_id}", response_model=VehicleDetailOut)
def get_vehicle(vehicle_id: int, db: DB, _user: CurrentUser) -> VehicleDetailOut:
    vehicle = _get_or_404(db, vehicle_id)
    return VehicleDetailOut(
        **VehicleOut.model_validate(vehicle).model_dump(),
        historico=clients_svc.work_order_history(db, vehicle_id=vehicle.id),
    )


@router.patch("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(vehicle_id: int, body: VehicleUpdateIn, db: DB, _user: CurrentUser) -> VehicleOut:
    vehicle = _get_or_404(db, vehicle_id)
    data = body.model_dump(exclude_unset=True, exclude={"remover_placa"})
    return VehicleOut.model_validate(_run(svc.update_vehicle, db, vehicle, data, remover_placa=body.remover_placa))


@router.post("/{vehicle_id}/arquivar", response_model=VehicleOut)
def archive_vehicle(vehicle_id: int, db: DB, _user: CurrentUser) -> VehicleOut:
    return VehicleOut.model_validate(_run(svc.archive_vehicle, db, _get_or_404(db, vehicle_id)))


@router.post("/{vehicle_id}/desarquivar", response_model=VehicleOut)
def unarchive_vehicle(vehicle_id: int, db: DB, _user: CurrentUser) -> VehicleOut:
    return VehicleOut.model_validate(_run(svc.unarchive_vehicle, db, _get_or_404(db, vehicle_id)))


@router.post("/{vehicle_id}/transferir", response_model=VehicleOut)
def transfer_vehicle(vehicle_id: int, body: VehicleTransferIn, db: DB, _user: CurrentUser) -> VehicleOut:
    vehicle = _get_or_404(db, vehicle_id)
    return VehicleOut.model_validate(_run(svc.transfer_vehicle, db, vehicle, new_client_id=body.client_id))


@router.delete("/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle_id: int, db: DB, _admin: AdminUser) -> None:
    svc.delete_vehicle(db, _get_or_404(db, vehicle_id))
