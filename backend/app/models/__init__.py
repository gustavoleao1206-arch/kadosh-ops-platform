"""Importa todos os modelos para que o Alembic e o create_all enxerguem as 11 tabelas."""

from app.models.auth import AuthLog, AuthSession
from app.models.client import Client
from app.models.enums import (
    AUTH_EVENTS,
    FORMAS_PAGAMENTO,
    ROLES,
    SESSION_CLIENTS,
    WORK_ORDER_EVENT_TYPES,
    WORK_ORDER_STATUSES,
)
from app.models.payment import Payment
from app.models.pricing import ClientServicePrice
from app.models.service import Service
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.work_order import WorkOrder, WorkOrderEvent, WorkOrderItem, work_order_numero_seq

__all__ = [
    "AUTH_EVENTS",
    "FORMAS_PAGAMENTO",
    "ROLES",
    "SESSION_CLIENTS",
    "WORK_ORDER_EVENT_TYPES",
    "WORK_ORDER_STATUSES",
    "AuthLog",
    "AuthSession",
    "Client",
    "ClientServicePrice",
    "Payment",
    "Service",
    "User",
    "Vehicle",
    "WorkOrder",
    "WorkOrderEvent",
    "WorkOrderItem",
    "work_order_numero_seq",
]
