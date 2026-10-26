"""Catálogo de serviços. Leitura para todos; alteração só para o admin (regra na rota)."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Service, WorkOrderItem


class CatalogError(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def list_services(
    db: Session, *, q: str | None, apenas_ativos: bool, page: int, page_size: int
) -> tuple[list[Service], int]:
    stmt = select(Service)
    if apenas_ativos:
        stmt = stmt.where(Service.ativo.is_(True))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                func.unaccent(func.lower(Service.nome)).ilike(func.unaccent(func.lower(like))),
                func.unaccent(func.lower(Service.descricao)).ilike(func.unaccent(func.lower(like))),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Service.ativo.desc(), func.unaccent(func.lower(Service.nome)), Service.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return rows, total


def get_service(db: Session, service_id: int) -> Service | None:
    return db.get(Service, service_id)


def _check_duplicate_name(db: Session, nome: str, *, exclude_id: int | None = None) -> None:
    stmt = select(Service.id).where(func.lower(Service.nome) == nome.lower())
    if exclude_id is not None:
        stmt = stmt.where(Service.id != exclude_id)
    if db.scalar(stmt):
        raise CatalogError("Já existe um serviço com este nome.", 409)


def create_service(db: Session, data: dict) -> Service:
    _check_duplicate_name(db, data["nome"])
    service = Service(**data)
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


def update_service(db: Session, service: Service, data: dict) -> Service:
    if "nome" in data and data["nome"].lower() != service.nome.lower():
        _check_duplicate_name(db, data["nome"], exclude_id=service.id)
    for field, value in data.items():
        setattr(service, field, value)
    db.commit()
    db.refresh(service)
    return service


def usage_count(db: Session, service_id: int) -> int:
    """Quantas OS já usaram este serviço (o histórico guarda nome e valor próprios)."""
    return db.scalar(select(func.count()).select_from(WorkOrderItem).where(WorkOrderItem.service_id == service_id)) or 0


def delete_service(db: Session, service: Service) -> None:
    """Só some do banco se nunca foi usado; caso contrário, desative (o histórico depende dele)."""
    if usage_count(db, service.id):
        raise CatalogError(
            "Este serviço já foi usado em ordens de serviço; desative-o em vez de excluir.", 409
        )
    db.delete(service)
    db.commit()
