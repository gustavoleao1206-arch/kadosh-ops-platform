from fastapi import APIRouter, HTTPException, Query

from app.core.deps import DB, AdminUser, CurrentUser
from app.schemas.catalog import ServiceCreateIn, ServiceOut, ServiceUpdateIn
from app.schemas.common import Page
from app.services import catalog as svc
from app.services import pricing as pricing_svc

router = APIRouter(prefix="/services", tags=["catálogo"])


def _get_or_404(db, service_id: int):
    service = svc.get_service(db, service_id)
    if service is None:
        raise HTTPException(404, "Serviço não encontrado.")
    return service


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except svc.CatalogError as e:
        raise HTTPException(e.status_code, e.detail) from e


@router.get("", response_model=Page[ServiceOut])
def list_services(
    db: DB,
    _user: CurrentUser,
    q: str | None = Query(None, max_length=120),
    apenas_ativos: bool = False,
    client_id: int | None = Query(None, description="preenche o preço combinado com este cliente"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
) -> Page[ServiceOut]:
    """Catálogo. Com `client_id`, cada serviço vem com o preço deste cliente e o que vale de fato.

    É o que o seletor da OS usa para já mostrar o preço certo — e para dizer de onde ele veio.
    """
    rows, total = svc.list_services(db, q=q, apenas_ativos=apenas_ativos, page=page, page_size=page_size)
    combinados = {}
    if client_id is not None:
        try:
            combinados = pricing_svc.precos_do_cliente(db, pricing_svc._cliente_ou_404(db, client_id).id)
        except pricing_svc.PricingError as e:
            raise HTTPException(e.status_code, e.detail) from e
    itens = []
    for s in rows:
        out = ServiceOut.model_validate(s)
        if client_id is not None:
            out.valor_cliente_centavos = combinados.get(s.id)
            out.valor_efetivo_centavos = pricing_svc.valor_efetivo(s, combinados.get(s.id))
        itens.append(out)
    return Page(items=itens, total=total, page=page, page_size=page_size)


@router.post("", response_model=ServiceOut, status_code=201)
def create_service(body: ServiceCreateIn, db: DB, _admin: AdminUser) -> ServiceOut:
    return ServiceOut.model_validate(_run(svc.create_service, db, body.model_dump()))


@router.get("/{service_id}", response_model=ServiceOut)
def get_service(service_id: int, db: DB, _user: CurrentUser) -> ServiceOut:
    return ServiceOut.model_validate(_get_or_404(db, service_id))


@router.patch("/{service_id}", response_model=ServiceOut)
def update_service(service_id: int, body: ServiceUpdateIn, db: DB, _admin: AdminUser) -> ServiceOut:
    service = _get_or_404(db, service_id)
    return ServiceOut.model_validate(_run(svc.update_service, db, service, body.model_dump(exclude_unset=True)))


@router.delete("/{service_id}", status_code=204)
def delete_service(service_id: int, db: DB, _admin: AdminUser) -> None:
    _run(svc.delete_service, db, _get_or_404(db, service_id))
