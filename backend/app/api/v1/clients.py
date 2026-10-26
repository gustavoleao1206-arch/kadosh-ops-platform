from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.core.deps import DB, AdminUser, CurrentUser
from app.schemas.clients import ClientCreateIn, ClientDetailOut, ClientOut, ClientUpdateIn, DuplicatePhoneOut
from app.schemas.pricing import ClientServicePriceIn, ClientServicePriceOut
from app.schemas.common import Page
from app.schemas.vehicles import VehicleOut
from app.services import clients as svc
from app.services import pricing as pricing_svc
from app.services import vehicles as vehicles_svc

router = APIRouter(prefix="/clients", tags=["clientes"])


def _get_or_404(db, client_id: int):
    client = svc.get_client(db, client_id)
    if client is None:
        raise HTTPException(404, "Cliente não encontrado.")
    return client


def _client_error(e: svc.ClientError):
    """409 de telefone repetido traz o cliente existente no corpo; os demais viram HTTPException."""
    if e.existing is not None:
        payload = DuplicatePhoneOut(detail=e.detail, existente=ClientOut.model_validate(e.existing))
        return JSONResponse(payload.model_dump(mode="json"), status_code=e.status_code)
    raise HTTPException(e.status_code, e.detail) from e


@router.get("", response_model=Page[ClientOut])
def list_clients(
    db: DB,
    _user: CurrentUser,
    q: str | None = Query(None, max_length=120),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    arquivados: bool = False,
) -> Page[ClientOut]:
    rows, total = svc.list_clients(db, q=q, page=page, page_size=page_size, arquivados=arquivados)
    return Page(items=[ClientOut.model_validate(c) for c in rows], total=total, page=page, page_size=page_size)


@router.post("", response_model=ClientOut, status_code=201, responses={409: {"model": DuplicatePhoneOut}})
def create_client(body: ClientCreateIn, db: DB, _user: CurrentUser, force: bool = False):
    try:
        client = svc.create_client(
            db, nome=body.nome, telefone=body.telefone, email=body.email, observacoes=body.observacoes, force=force
        )
    except svc.ClientError as e:
        return _client_error(e)
    return ClientOut.model_validate(client)


@router.get("/{client_id}", response_model=ClientDetailOut)
def get_client(client_id: int, db: DB, _user: CurrentUser) -> ClientDetailOut:
    client = _get_or_404(db, client_id)
    return ClientDetailOut(
        **ClientOut.model_validate(client).model_dump(),
        stats=svc.client_stats(db, client.id),
        historico=svc.work_order_history(db, client_id=client.id),
    )


@router.patch("/{client_id}", response_model=ClientOut, responses={409: {"model": DuplicatePhoneOut}})
def update_client(client_id: int, body: ClientUpdateIn, db: DB, _user: CurrentUser, force: bool = False):
    client = _get_or_404(db, client_id)
    data = body.model_dump(exclude_unset=True)
    try:
        return ClientOut.model_validate(svc.update_client(db, client, data, force=force))
    except svc.ClientError as e:
        return _client_error(e)


@router.post("/{client_id}/arquivar", response_model=ClientOut)
def archive_client(client_id: int, db: DB, _user: CurrentUser) -> ClientOut:
    try:
        return ClientOut.model_validate(svc.archive_client(db, _get_or_404(db, client_id)))
    except svc.ClientError as e:
        raise HTTPException(e.status_code, e.detail) from e


@router.post("/{client_id}/desarquivar", response_model=ClientOut)
def unarchive_client(client_id: int, db: DB, _user: CurrentUser) -> ClientOut:
    return ClientOut.model_validate(svc.unarchive_client(db, _get_or_404(db, client_id)))


@router.delete("/{client_id}", status_code=204)
def delete_client(client_id: int, db: DB, _admin: AdminUser) -> None:
    svc.delete_client(db, _get_or_404(db, client_id))


@router.get("/{client_id}/vehicles", response_model=list[VehicleOut])
def client_vehicles(client_id: int, db: DB, _user: CurrentUser, arquivados: bool = False) -> list[VehicleOut]:
    _get_or_404(db, client_id)
    rows, _ = vehicles_svc.list_vehicles(db, q=None, client_id=client_id, page=1, page_size=200, arquivados=arquivados)
    return [VehicleOut.model_validate(v) for v in rows]


# ------------------------------------------------------------------ preços combinados


def _pricing(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except pricing_svc.PricingError as e:
        raise HTTPException(e.status_code, e.detail) from e


@router.get("/{client_id}/service-prices", response_model=list[ClientServicePriceOut])
def list_service_prices(client_id: int, db: DB, _user: CurrentUser) -> list[ClientServicePriceOut]:
    """O catálogo ativo visto por este cliente: preço de tabela, o dele e o que vale.

    Leitura liberada ao sócio — ele precisa saber por que a OS veio com outro preço; escrever é do
    administrador, porque preço combinado é extensão do catálogo.
    """
    _pricing(pricing_svc._cliente_ou_404, db, client_id)
    return [ClientServicePriceOut(**linha) for linha in pricing_svc.listar(db, client_id)]


@router.put("/{client_id}/service-prices/{service_id}", response_model=ClientServicePriceOut)
def set_service_price(
    client_id: int, service_id: int, body: ClientServicePriceIn, db: DB, admin: AdminUser
) -> ClientServicePriceOut:
    """Define quanto ESTE cliente paga neste serviço, das próximas OS em diante.

    Sem chave de idempotência de propósito: é um upsert, mandar duas vezes dá no mesmo. Chave só
    existe onde repetir CRIA valor — pagamento e item.
    """
    return ClientServicePriceOut(
        **_pricing(pricing_svc.definir, db, client_id, service_id, body.valor_centavos, user=admin)
    )


@router.delete("/{client_id}/service-prices/{service_id}", status_code=204)
def delete_service_price(client_id: int, service_id: int, db: DB, _admin: AdminUser) -> None:
    """Volta este cliente ao preço de tabela. As OS já lançadas ficam como estão."""
    _pricing(pricing_svc.remover, db, client_id, service_id)
