"""
Prometheus metrics endpoint.

Mounted at ``/metrics`` (root level) for Prometheus scrape targets.
No auth required.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import REGISTRY, CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    """Return all registered Prometheus metrics in text format."""
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )
