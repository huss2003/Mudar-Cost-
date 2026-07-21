"""
AI Features Router — intelligent project analysis endpoints.

All endpoints under ``/api/v1/ai``:

- ``POST /projects/{project_id}/ask`` — Natural-language Q&A
- ``POST /projects/{project_id}/missing-boq`` — Missing BOQ item detection
- ``POST /projects/{project_id}/anomalies`` — Anomaly detection vs historical data
- ``POST /projects/{project_id}/value-engineering`` — Cost-saving suggestions
- ``POST /projects/{project_id}/duration-predict`` — Duration prediction
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.database import async_session
from app.models.core import Project
from app.schemas.ai_features import (
    AnomalyResponse,
    AskRequest,
    AskResponse,
    DurationPredictResponse,
    MissingBOQResponse,
    VEResponse,
)
from app.services.ai_feature_service import (
    answer_project_question,
    detect_anomalies,
    detect_missing_boq_items,
    predict_duration,
    suggest_value_engineering,
)
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["ai-features"])


# ---------------------------------------------------------------------------
# Helper: verify project exists
# ---------------------------------------------------------------------------


async def _get_project_or_404(project_id: int):
    """Raise 404 if the project doesn't exist."""
    async with async_session() as db:
        result = await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.is_deleted == False,  # noqa: E712
            )
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise HTTPException(
                status_code=404,
                detail=f"Project {project_id} not found",
            )


# ======================================================================
# POST /projects/{project_id}/ask — Natural-language Q&A
# ======================================================================


@router.post(
    "/projects/{project_id}/ask",
    response_model=AskResponse,
    summary="Ask a natural-language question about the project",
)
async def ask_question(project_id: int, body: AskRequest):
    """Answer a natural-language question about the project's BOQ, costs,
    materials, and similar projects.

    Supports streaming (SSE) when ``stream=true``.
    """
    await _get_project_or_404(project_id)

    if body.stream:
        return await _stream_answer(project_id, body.question)

    async with async_session() as db:
        result = await answer_project_question(
            db, project_id, body.question, stream=False
        )
    return result


async def _stream_answer(project_id: int, question: str) -> EventSourceResponse:
    """Stream the answer via Server-Sent Events."""

    async def event_generator() -> AsyncIterator[dict]:
        async with async_session() as db:
            result = await answer_project_question(
                db, project_id, question, stream=False
            )
            # Yield the full answer as SSE events (one word per event)
            answer_text = result.answer
            words = answer_text.split(" ")
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                yield {"event": "chunk", "data": chunk}
            # Final metadata event
            yield {
                "event": "done",
                "data": str({
                    "confidence": result.confidence,
                    "sources": result.sources,
                }),
            }

    return EventSourceResponse(event_generator())


# ======================================================================
# POST /projects/{project_id}/missing-boq — Detect missing BOQ items
# ======================================================================


@router.post(
    "/projects/{project_id}/missing-boq",
    response_model=MissingBOQResponse,
    summary="Detect missing BOQ items vs detected objects & similar projects",
)
async def missing_boq(project_id: int):
    """Analyse the current BOQ against detected objects and similar completed
    projects to identify gaps. Returns suggested items with estimated quantities."""
    await _get_project_or_404(project_id)

    async with async_session() as db:
        result = await detect_missing_boq_items(db, project_id)
    return result


# ======================================================================
# POST /projects/{project_id}/anomalies — Detect anomalies vs past projects
# ======================================================================


@router.post(
    "/projects/{project_id}/anomalies",
    response_model=AnomalyResponse,
    summary="Detect cost/quantity anomalies vs historical data",
)
async def anomalies(project_id: int):
    """Compare the current project's rates, quantities, and material selections
    against similar completed projects. Flags items where the rate deviates by
    more than 20% from the historical average, quantity mismatches with detected
    objects, and missing material categories."""
    await _get_project_or_404(project_id)

    async with async_session() as db:
        result = await detect_anomalies(db, project_id)
    return result


# ======================================================================
# POST /projects/{project_id}/value-engineering — Cost-saving suggestions
# ======================================================================


@router.post(
    "/projects/{project_id}/value-engineering",
    response_model=VEResponse,
    summary="Suggest cost-saving material alternatives",
)
async def value_engineering(project_id: int):
    """For each BOQ item with an assigned material, find cheaper alternatives
    in the same category. Returns the top 10 suggestions ranked by potential
    savings, with implementation effort and risk estimates."""
    await _get_project_or_404(project_id)

    async with async_session() as db:
        result = await suggest_value_engineering(db, project_id, top_k=10)
    return result


# ======================================================================
# POST /projects/{project_id}/duration-predict — Predict project duration
# ======================================================================


@router.post(
    "/projects/{project_id}/duration-predict",
    response_model=DurationPredictResponse,
    summary="Predict project duration based on BOQ quantities",
)
async def duration_predict(project_id: int):
    """Estimate the total project duration by:
    1. Grouping BOQ items by trade
    2. Querying ProductivityRate (output_per_day) for each trade
    3. Computing duration = total_quantity / (output_per_day × crew_size)
    4. Applying sequential/parallel trade dependencies
    5. Identifying the critical path

    Returns total days, per-trade breakdown, Gantt chart data, and the
    critical path. Falls back to sensible defaults when productivity
    rates are not in the database."""
    await _get_project_or_404(project_id)

    async with async_session() as db:
        result = await predict_duration(db, project_id)
    return result
