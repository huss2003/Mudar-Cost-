"""
Celery monitoring endpoints.

Provides a lightweight health-check that reports active Celery workers.
Useful for load-balancer probes and operational dashboards.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/celery", tags=["celery"])


@router.get("/health")
async def celery_health():
    """Check Celery worker status.

    Uses the Celery inspect API to query active workers.  Returns an empty
    list when no workers are connected (the backend is still healthy, just
    not currently processing anything).
    """
    try:
        i = celery_app.control.inspect()
        active = i.active()
        workers = list(active.keys()) if active else []
        return {"status": "ok", "active_workers": workers}
    except Exception as exc:
        logger.warning("Celery health check failed: %s", exc)
        return {"status": "unreachable", "active_workers": [], "detail": str(exc)}
