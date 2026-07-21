"""SSE (Server-Sent Events) live-update router.

Provides a streaming endpoint that pushes cost recalculations to frontend
clients when materials are selected.

Endpoints (all mounted under ``/api/v1`` via ``main.py``):

- ``GET /projects/{project_id}/live`` — SSE event stream
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.services.live_update import publish, subscribe, unsubscribe

logger = logging.getLogger(__name__)

router = APIRouter(tags=["live"])

# How long (seconds) to wait between messages before sending a heartbeat.
# Keeps the connection alive through proxies and load balancers.
_HEARTBEAT_INTERVAL = 30.0


@router.get("/projects/{project_id}/live")
async def sse_stream(project_id: int):
    """SSE endpoint: pushes live cost-update events for *project_id*.

    The client receives the following event types:

    ``connected``
        Initial confirmation — fired as soon as the stream is established.
        Payload: ``{\"project_id\": <int>}``

    ``heartbeat``
        Sent every 30 s when no other events occur.  Keeps load-balancer /
        reverse-proxy timeouts at bay.
        Payload: ``{}``

    ``material_changed``
        Fired after a material selection.  Contains the updated line-item
        total and the new project-wide grand total.
        Payload: ``{\"boq_item_id\": int, \"line_total\": float,
        \"line_description\": str, \"project_total\": float,
        \"total_items\": int}``

    ``cost_update``
        Fired after every material change.  Carries full trade-group
        aggregations and per-item cost breakdowns so the frontend can
        refresh its entire cost view.
        Payload: ``{\"trade_groups\": [...], \"cost_breakdowns\": [...],
        \"project_total\": float, \"total_items\": int}``

    When the client disconnects the subscriber queue is automatically
    cleaned up.
    """
    queue = subscribe(project_id)

    async def event_generator():
        try:
            # 1. Connection confirmation
            yield (
                f"event: connected\n"
                f"data: {json.dumps({'project_id': project_id})}\n\n"
            )

            while True:
                try:
                    message = await asyncio.wait_for(
                        queue.get(), timeout=_HEARTBEAT_INTERVAL
                    )
                    yield (
                        f"event: {message['event']}\n"
                        f"data: {json.dumps(message['data'])}\n\n"
                    )
                except asyncio.TimeoutError:
                    # Heartbeat — keeps the connection alive through proxies
                    yield f"event: heartbeat\ndata: {{}}\n\n"
        except asyncio.CancelledError:
            # Client disconnected — clean up below
            pass
        finally:
            unsubscribe(project_id, queue)
            logger.debug("SSE stream closed for project %d", project_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
