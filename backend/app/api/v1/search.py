from fastapi import APIRouter, Query

from app.core.deps import DB, CurrentUser
from app.schemas.clients import ClientOut
from app.schemas.search import SearchOut
from app.schemas.vehicles import VehicleOut
from app.services import search as svc

router = APIRouter(prefix="/search", tags=["busca"])


@router.get("", response_model=SearchOut)
def search(db: DB, _user: CurrentUser, q: str = Query(..., min_length=1, max_length=120)) -> SearchOut:
    vehicles, clients = svc.search(db, q)
    return SearchOut(
        q=q,
        veiculos=[VehicleOut.model_validate(v) for v in vehicles],
        clientes=[ClientOut.model_validate(c) for c in clients],
    )
