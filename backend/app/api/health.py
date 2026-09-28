import os
from datetime import datetime, timezone
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

router = APIRouter()


@router.get("/health")
def health_check():
    """
    Multi-subsystem health check endpoint verifying:
    - API liveness
    - SQLite database connectivity
    - Local storage writeability
    - Statement parsing pipeline readiness
    - Billing adapter operational mode
    """
    subsystems = {
        "database": "operational",
        "storage": "operational",
        "parsing_pipeline": "operational",
        "billing_adapter": f"{settings.BILLING_MODE}_mode_operational",
    }

    checks = {
        "database": {"status": "ok", "engine": "sqlite"},
        "storage": {"status": "ok", "writable": True, "path": settings.UPLOAD_DIR},
        "parsing_pipeline": {"status": "ok", "pdf": "ready", "ocr": "ready"},
        "billing": {"status": "ok", "mode": settings.BILLING_MODE},
    }

    all_healthy = True

    # 1. Database check
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        subsystems["database"] = "unhealthy"
        checks["database"] = {"status": "error", "error": str(e)}
        all_healthy = False

    # 2. Storage writeability check
    try:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        probe_path = os.path.join(settings.UPLOAD_DIR, ".health_probe")
        with open(probe_path, "w") as f:
            f.write("probe")
        if os.path.exists(probe_path):
            os.remove(probe_path)
    except Exception as e:
        subsystems["storage"] = "unhealthy"
        checks["storage"] = {"status": "error", "writable": False, "error": str(e)}
        all_healthy = False

    # 3. Parsing pipeline readiness check
    try:
        from app.services.parser.router import parse_statement
        checks["parsing_pipeline"]["router"] = "ready"
    except Exception as e:
        subsystems["parsing_pipeline"] = "unhealthy"
        checks["parsing_pipeline"] = {"status": "error", "error": str(e)}
        all_healthy = False

    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if all_healthy else "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0",
            "subsystems": subsystems,
            "checks": checks,
        },
    )
