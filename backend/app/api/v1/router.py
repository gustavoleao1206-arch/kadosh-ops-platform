from fastapi import APIRouter

from app.api.v1 import auth, catalog, clients, finance, health, reports, search, users, vehicles, work_orders

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(clients.router)
api_router.include_router(vehicles.router)
api_router.include_router(catalog.router)
api_router.include_router(work_orders.router)
api_router.include_router(finance.router)
api_router.include_router(reports.router)
api_router.include_router(search.router)
