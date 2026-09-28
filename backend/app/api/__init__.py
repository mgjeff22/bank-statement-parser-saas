from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.statements import router as statements_router
from app.api.health import router as health_router

__all__ = [
    "auth_router",
    "dashboard_router",
    "statements_router",
    "health_router",
]
