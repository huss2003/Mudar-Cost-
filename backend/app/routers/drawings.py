"""Drawing upload, status, and object endpoints.

Provides the following routes under ``/api/v1/drawings``:

- ``POST /`` — multipart file upload → magic check → streaming → MinIO +
  SHA-256 dedup → structural sanity → route selection → Celery dispatch
- ``GET /`` — list all drawings (summary)
- ``GET /types`` — catalogue of known object types
- ``GET /{drawing_id}`` — single drawing metadata
- ``GET /{drawing_id}/status`` — processing status with object count
- ``GET /{drawing_id}/objects`` — detected objects for a drawing
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, File, Query, UploadFile

from app.celery_app import celery_app
from app.database import async_session
from app.models.core import Drawing
from app.models.reference import DrawingObjectType
from app.schemas.detection import (
    DrawingObjectResponse,
    DrawingStatusResponse,
    DrawingUploadResponse,
)
from app.services.drawing_service import (
    create_drawing,
    get_drawing_objects,
    get_drawing_status,
)
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drawings", tags=["drawings"])


# ======================================================================
# POST /drawings — Upload a file
# ======================================================================


@router.post("", response_model=DrawingUploadResponse, status_code=201)
async def upload_drawing(
    file: UploadFile = File(..., description="Drawing file (.dxf, .dwg, .pdf, .png, .jpg)"),
    project_id: int = Query(
        ...,
        description="Project ID to associate this drawing with",
    ),
) -> DrawingUploadResponse:
    """Upload a CAD drawing or PDF floor plan.

    The enhanced upload pipeline:

    1. Magic-byte / MIME validation on the header bytes.
    2. Streaming upload to a temp file + progressive SHA-256 hashing.
    3. SHA-256 dedup check — if the same file already exists in the
       project, return the existing record (no re-upload).
    4. Filename sanitization (strip path-traversal characters).
    5. EXIF metadata stripping from image files.
    6. Structural sanity check — PDFs without vector content are
       routed to the AI vision pipeline.
    7. Streaming upload to MinIO (O(1) memory).
    8. DB record creation with sha256_hash.
    9. Dispatch to appropriate Celery task based on ``routing_hint``:

       - ``cad_parser`` → ``app.tasks.drawings.process_drawing``
       - ``ai_vision`` / ``image`` → ``app.tasks.ai_drawings.process_drawing_ai``
       - ``existing`` → skip dispatch (dedup hit)
    """
    # 1. Upload to MinIO & create DB record (handles all validation)
    response = await create_drawing(file=file, project_id=project_id)

    # 2. Skip Celery dispatch for dedup hits
    if response.routing_hint == "existing":
        logger.info(
            "Dedup hit for drawing %d — skipping Celery dispatch",
            response.drawing_id,
        )
        return response

    # 3. Fetch the full DB record for the Celery task args
    async with async_session() as db:
        result = await db.execute(
            select(Drawing).where(
                Drawing.id == response.drawing_id,
                Drawing.is_deleted == False,
            )
        )
        drawing = result.scalar_one_or_none()
        if drawing is None:
            logger.error("Drawing %s vanished after create", response.drawing_id)
            return response  # return without job_id

    # 4. Dispatch to the appropriate task
    task_name = _select_task(response.routing_hint)
    task = celery_app.send_task(
        task_name,
        args=[drawing.id, drawing.minio_object_key, drawing.file_type],
    )
    logger.info(
        "Dispatched Celery task %s (%s) for drawing %d",
        task.id,
        task_name,
        drawing.id,
    )

    response.job_id = task.id
    return response


def _select_task(routing_hint: str | None) -> str:
    """Map a routing hint to the corresponding Celery task name.

    - ``cad_parser`` → rule-based CAD/PDF parsing task.
    - ``ai_vision`` or ``image`` → AI vision enhancement pipeline.
    - ``unknown`` or ``None`` → default to rule-based parser.
    """
    if routing_hint in ("ai_vision", "image"):
        return "app.tasks.ai_drawings.process_drawing_ai"
    return "app.tasks.drawings.process_drawing"


# ======================================================================
# GET /drawings — List all drawings
# ======================================================================


@router.get("")
async def list_drawings():
    """List all uploaded drawings (summary metadata)."""
    async with async_session() as db:
        result = await db.execute(
            select(Drawing)
            .where(Drawing.is_deleted == False)
            .order_by(Drawing.created_at.desc())
        )
        drawings = result.scalars().all()

    return {
        "drawings": [
            {
                "id": d.id,
                "filename": d.filename,
                "file_type": d.file_type,
                "file_size_bytes": d.file_size_bytes,
                "status": d.status,
                "project_id": d.project_id,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "processed_at": d.processed_at.isoformat() if d.processed_at else None,
            }
            for d in drawings
        ],
        "total": len(drawings),
    }


# ======================================================================
# GET /drawings/types — Catalogue of known object types
# ======================================================================


@router.get("/types")
async def list_object_types():
    """Return all known drawing object types from the catalogue.

    Each entry contains the type name, display name, category, and
    default unit for measurement.
    """
    async with async_session() as db:
        result = await db.execute(
            select(DrawingObjectType)
            .where(DrawingObjectType.is_deleted == False)
            .order_by(DrawingObjectType.name)
        )
        types = result.scalars().all()

    return [
        {
            "name": t.name,
            "display_name": t.display_name,
            "category": t.category,
            "default_unit": t.default_unit,
        }
        for t in types
    ]


# ======================================================================
# GET /drawings/{drawing_id} — Single drawing metadata
# ======================================================================


@router.get("/{drawing_id}")
async def get_drawing(drawing_id: int):
    """Get metadata for a single drawing."""
    async with async_session() as db:
        result = await db.execute(
            select(Drawing).where(
                Drawing.id == drawing_id,
                Drawing.is_deleted == False,
            )
        )
        drawing = result.scalar_one_or_none()

    if drawing is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Drawing {drawing_id} not found")

    return {
        "id": drawing.id,
        "filename": drawing.filename,
        "file_type": drawing.file_type,
        "file_size_bytes": drawing.file_size_bytes,
        "minio_object_key": drawing.minio_object_key,
        "status": drawing.status,
        "project_id": drawing.project_id,
        "description": drawing.description,
        "page_count": drawing.page_count,
        "revision": drawing.revision,
        "error_message": drawing.error_message,
        "created_at": drawing.created_at.isoformat() if drawing.created_at else None,
        "updated_at": drawing.updated_at.isoformat() if drawing.updated_at else None,
        "processed_at": drawing.processed_at.isoformat() if drawing.processed_at else None,
    }


# ======================================================================
# GET /drawings/{drawing_id}/status — Processing status
# ======================================================================


@router.get("/{drawing_id}/status", response_model=DrawingStatusResponse)
async def drawing_status(drawing_id: int) -> DrawingStatusResponse:
    """Return the current processing status for a drawing.

    Includes the number of detected objects found so far and any
    error message if processing failed.
    """
    return await get_drawing_status(drawing_id)


# ======================================================================
# GET /drawings/{drawing_id}/objects — Detected objects
# ======================================================================


@router.get("/{drawing_id}/objects", response_model=List[DrawingObjectResponse])
async def drawing_objects(drawing_id: int) -> List[DrawingObjectResponse]:
    """Return all detected objects for a drawing.

    Each object includes type, dimensions, location, confidence,
    and bounding-box coordinates.
    """
    return await get_drawing_objects(drawing_id)
