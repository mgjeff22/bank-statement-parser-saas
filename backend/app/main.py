from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.statements import router as statements_router
from app.api.health import router as health_router
from app.api.billing import router as billing_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    init_db()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Multimodal Bank Statement Parsing & Reconciliation SaaS API",
    version="1.0.0",
    lifespan=lifespan,
)

# Custom exception handler to unroll dictionary details (e.g. QUOTA_EXCEEDED) to root JSON
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        content = exc.detail.copy()
        if "detail" not in content:
            content["detail"] = exc.detail.get("message", "Error")
        return JSONResponse(status_code=exc.status_code, content=content)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


from app.api.export import router as export_router
from app.api.transactions import router as transactions_router
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(statements_router, prefix="/api/statements", tags=["statements"])
app.include_router(transactions_router, prefix="/api/statements", tags=["transactions"])
app.include_router(export_router, prefix="/api/export", tags=["export"])
app.include_router(billing_router, prefix="/api/billing", tags=["billing"])
app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(health_router, prefix="", tags=["health"])  # Also exposed at /health

# Mount static frontend build if present
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.exists(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Allow API requests and documentation to pass through
        if full_path.startswith("api/") or full_path in ("docs", "redoc", "openapi.json"):
            raise HTTPException(status_code=404, detail="Not Found")
        target_file = os.path.join(frontend_dist, full_path)
        if os.path.isfile(target_file):
            return FileResponse(target_file)
        return FileResponse(os.path.join(frontend_dist, "index.html"))

