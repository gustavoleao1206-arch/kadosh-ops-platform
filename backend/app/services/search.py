"""Busca única do pátio: placa parcial, dígitos do telefone, nome do dono, modelo ou marca. Só ativos."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.text import only_digits, placa_fragment
from app.models import Client, Vehicle

LIMIT = 20


def search(db: Session, q: str) -> tuple[list[Vehicle], list[Client]]:
    q = q.strip()
    if len(q) < 2:
        return [], []
    like = f"%{q}%"
    digits = only_digits(q)
    placa = placa_fragment(q)

    v_conds = [
        func.unaccent(func.lower(Vehicle.modelo)).ilike(func.unaccent(func.lower(like))),
        func.unaccent(func.lower(Vehicle.marca)).ilike(func.unaccent(func.lower(like))),
        func.unaccent(func.lower(Client.nome)).ilike(func.unaccent(func.lower(like))),
    ]
    if placa:
        v_conds.append(Vehicle.placa.contains(placa))
    if len(digits) >= 4:
        v_conds.append(Client.telefone.contains(digits))
    vehicles = db.scalars(
        select(Vehicle)
        .join(Client, Client.id == Vehicle.client_id)
        .options(selectinload(Vehicle.client))
        .where(Vehicle.arquivado_em.is_(None), Client.arquivado_em.is_(None), or_(*v_conds))
        .order_by(Vehicle.id.desc())
        .limit(LIMIT)
    ).all()

    c_conds = [func.unaccent(func.lower(Client.nome)).ilike(func.unaccent(func.lower(like)))]
    if len(digits) >= 4:
        c_conds.append(Client.telefone.contains(digits))
    clients = db.scalars(
        select(Client)
        .options(selectinload(Client.vehicles))
        .where(Client.arquivado_em.is_(None), or_(*c_conds))
        .order_by(func.unaccent(func.lower(Client.nome)), Client.id)
        .limit(LIMIT)
    ).all()
    return vehicles, clients
