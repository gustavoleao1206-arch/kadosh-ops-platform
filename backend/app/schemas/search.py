from app.schemas.base import OutSchema
from app.schemas.clients import ClientOut
from app.schemas.vehicles import VehicleOut


class SearchOut(OutSchema):
    """Busca única: placa parcial, dígitos do telefone ou nome — veículos já vêm com o cliente."""

    q: str
    veiculos: list[VehicleOut]
    clientes: list[ClientOut]
