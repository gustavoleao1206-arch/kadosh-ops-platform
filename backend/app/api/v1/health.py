from fastapi import APIRouter, Response
from sqlalchemy import text

from app import __version__
from app.core.deps import DB

router = APIRouter(tags=["saúde"])


@router.get("/health")
def health(db: DB, response: Response) -> dict:
    """Usado pelo Render para saber se o serviço está saudável (inclui o banco)."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:  # noqa: BLE001
        db_status = "erro"
        response.status_code = 503
    return {"status": "ok" if db_status == "ok" else "degradado", "db": db_status, "version": __version__}
