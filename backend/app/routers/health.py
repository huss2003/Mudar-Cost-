"""
Health / readiness probe endpoints (no auth required).

Mounted at root level (``/healthz``, ``/readyz``) so load balancers and
Kubernetes can reach them without authentication.
"""

from __future__ import annotations

from datetime import datetime

import redis as redis_lib
import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.celery_app import celery_app
from app.config import settings
from app.database import async_session
from app.minio_client import get_minio_client

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def liveness() -> dict:
    """Liveness probe — always 200 if the process is alive."""
    return {
        "status": "alive",
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/readyz")
async def readiness() -> JSONResponse:
    """Readiness probe — deep check of all dependencies.

    Returns ``200`` when every dependency is healthy, ``503`` when one
    or more dependencies are unreachable or degraded.
    """
    checks: dict[str, dict] = {}

    # --- PostgreSQL -------------------------------------------------------
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        checks["postgres"] = {"status": "ok"}
    except Exception as exc:
        checks["postgres"] = {"status": "error", "error": str(exc)}
        logger.warning("readiness: postgres check failed", error=str(exc))

    # --- MinIO ------------------------------------------------------------
    try:
        mc = get_minio_client()
        mc.list_buckets()
        checks["minio"] = {"status": "ok"}
    except Exception as exc:
        checks["minio"] = {"status": "error", "error": str(exc)}
        logger.warning("readiness: minio check failed", error=str(exc))

    # --- Redis ------------------------------------------------------------
    try:
        r = redis_lib.from_url(settings.REDIS_URL)
        r.ping()
        checks["redis"] = {"status": "ok"}
    except Exception as exc:
        checks["redis"] = {"status": "error", "error": str(exc)}
        logger.warning("readiness: redis check failed", error=str(exc))

    # --- Celery -----------------------------------------------------------
    try:
        i = celery_app.control.inspect()
        active = i.active()
        checks["celery"] = {
            "status": "ok" if active is not None else "degraded",
        }
    except Exception as exc:
        checks["celery"] = {"status": "error", "error": str(exc)}
        logger.warning("readiness: celery check failed", error=str(exc))

    # --- Aggregate result -------------------------------------------------
    all_ok = all(c["status"] == "ok" for c in checks.values())
    status_code = 200 if all_ok else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ok else "degraded",
            "checks": checks,
        },
    )
