"""Business logic for drawing upload and processing workflow.

The upload pipeline enforces:

1. **Empty file check** — reject 0-byte uploads immediately.
2. **Magic-byte / MIME validation** — verify header bytes match the
   declared extension *before* streaming the full payload.
3. **Streaming to temp file + progressive SHA-256** — never hold the
   entire file in memory; compute the hash while writing to disk.
4. **SHA-256 dedup** — if a drawing with the same hash already exists for
   the same project, return the existing record instead of re-uploading.
5. **Filename sanitization** — strip path-traversal / dangerous chars.
6. **EXIF stripping** — remove metadata from image files.
7. **Structural sanity check** — verify PDF/DXF contain parseable content.
8. **Raster-only → AI vision routing** — PDFs without vector content are
   routed to the AI vision pipeline instead of the CAD parser.
9. **Streaming upload to MinIO** — upload from the temp file, O(1) memory.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.minio_client import get_minio_client
from app.models.core import Drawing
from app.models.detection import DetectedObject
from app.schemas.detection import (
    DrawingObjectResponse,
    DrawingStatusResponse,
    DrawingUploadResponse,
)
from app.services.file_sanity import (
    check_dwg_has_content,
    check_dxf_has_content,
    check_pdf_has_content,
)
from app.services.upload_validation import (
    check_magic_bytes,
    sanitize_filename,
    strip_exif,
    validate_upload_file,
)

logger = logging.getLogger(__name__)

# Number of bytes to read for the initial magic-byte check
_HEADER_BYTES = 64

# Chunk size for streaming reads (8 KB)
_CHUNK_SIZE = 8192


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------


async def create_drawing(
    file: UploadFile,
    project_id: int,
) -> DrawingUploadResponse:
    """Upload a drawing file to MinIO, create a DB record, and return metadata.

    Steps
    -----
    1. Validate file extension (dxf / dwg / pdf).
    2. Read header bytes for magic-byte/MIME validation.
    3. Stream remaining content to a temp file, computing SHA-256.
    4. Check for duplicate by SHA-256 hash within the project.
    5. Sanitize the filename.
    6. Strip EXIF from images.
    7. Run structural sanity check (PDF/DXF).
    8. Route: vector content → CAD parser; raster-only → AI vision.
    9. Stream temp file to MinIO (O(1) memory).
    10. Create ``Drawing`` row in PostgreSQL with ``sha256_hash``.
    11. Return the drawing metadata with hash and routing hint.

    Parameters
    ----------
    file:
        The uploaded multipart file.
    project_id:
        The project to associate this drawing with (DB FK, required).

    Returns
    -------
    DrawingUploadResponse
        With the drawing ID, filename, SHA-256 hash, routing hint,
        status, and a placeholder for the Celery task ID (filled in
        by the caller).
    """
    temp_path: str | None = None

    try:
        # ==================================================================
        # 0. Quick empty check (before any reads)
        # ==================================================================
        header = await file.read(_HEADER_BYTES)
        if not header:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty",
            )

        # ==================================================================
        # 1. Magic-byte / MIME validation
        # ==================================================================
        magic_error = check_magic_bytes(file.filename or "", header)
        if magic_error:
            raise HTTPException(status_code=400, detail=magic_error)

        # ==================================================================
        # 2. Stream to temp file + progressive SHA-256
        # ==================================================================
        sha = hashlib.sha256()
        sha.update(header)  # include the header bytes we already read

        # Create a temp file in the system temp dir
        fd, temp_path = tempfile.mkstemp(suffix=".upload")
        os.close(fd)

        file_size = len(header)
        with open(temp_path, "wb") as tmp:
            tmp.write(header)
            while chunk := await file.read(_CHUNK_SIZE):
                sha.update(chunk)
                tmp.write(chunk)
                file_size += len(chunk)

        computed_hash = sha.hexdigest()

        # ==================================================================
        # 3. Extension + size validation (now that we know file_size)
        # ==================================================================
        ext_error = validate_upload_file(file.filename or "", file_size)
        if ext_error:
            raise HTTPException(status_code=400, detail=ext_error)

        # ==================================================================
        # 4. SHA-256 dedup check
        # ==================================================================
        existing = await _find_existing_by_hash(computed_hash, project_id)
        if existing is not None:
            logger.info(
                "Dedup hit: drawing %s hash=%s already exists for project %d",
                existing.filename,
                computed_hash[:12],
                project_id,
            )
            return DrawingUploadResponse(
                drawing_id=existing.id,
                filename=existing.filename,
                sha256_hash=computed_hash,
                status=existing.status,
                job_id=None,
                routing_hint="existing",
                message="Duplicate file — returning existing drawing record",
            )

        # ==================================================================
        # 5. Derive file type & sanitize filename
        # ==================================================================
        from pathlib import Path as _Path

        ext = _Path(file.filename or "").suffix.lower()
        file_type = ext.lstrip(".")
        safe_filename = sanitize_filename(file.filename or "uploaded_file")
        # Preserve the original extension in the safe name
        if not safe_filename.endswith(ext):
            safe_filename = safe_filename + ext

        # ==================================================================
        # 6. Strip EXIF from image files
        # ==================================================================
        strip_exif(temp_path)

        # ==================================================================
        # 7. Structural sanity check & routing
        # ==================================================================
        routing_hint = _run_sanity_check(temp_path, file_type)

        # ==================================================================
        # 8. Generate MinIO object key & stream upload
        # ==================================================================
        object_key = f"drawings/{uuid.uuid4()}_{safe_filename}"

        mc = get_minio_client()
        loop = asyncio.get_running_loop()

        # Stream from temp file — O(1) memory
        await loop.run_in_executor(
            None,
            lambda: mc.fput_object(
                settings.MINIO_BUCKET,
                object_key,
                temp_path,
            ),
        )

        logger.info(
            "Uploaded %s to MinIO bucket %s as %s (hash=%s, route=%s)",
            safe_filename,
            settings.MINIO_BUCKET,
            object_key,
            computed_hash[:12],
            routing_hint,
        )

        # ==================================================================
        # 9. Create DB record
        # ==================================================================
        drawing = Drawing(
            filename=safe_filename,
            file_type=file_type,
            minio_object_key=object_key,
            file_size_bytes=file_size,
            sha256_hash=computed_hash,
            status="uploaded",
            project_id=project_id,
        )

        async with async_session() as db:
            db.add(drawing)
            await db.commit()
            await db.refresh(drawing)

        logger.info(
            "Drawing record created: id=%d filename=%s hash=%s",
            drawing.id,
            drawing.filename,
            computed_hash[:12],
        )

        return DrawingUploadResponse(
            drawing_id=drawing.id,
            filename=drawing.filename,
            sha256_hash=computed_hash,
            status=drawing.status,
            job_id=None,  # Caller (router) fills this after task dispatch
            routing_hint=routing_hint,
            message="File uploaded. Processing started.",
        )

    finally:
        # Always clean up the temp file
        if temp_path is not None and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError as rm_err:
                logger.warning(
                    "Could not remove temp file %s: %s",
                    temp_path,
                    rm_err,
                )


# ---------------------------------------------------------------------------
# Dedup helper
# ---------------------------------------------------------------------------


async def _find_existing_by_hash(
    sha256_hash: str,
    project_id: int,
) -> Drawing | None:
    """Check whether a drawing with *sha256_hash* already exists in *project_id*.

    Returns the existing ``Drawing`` row if found, else ``None``.
    """
    async with async_session() as db:
        result = await db.execute(
            select(Drawing).where(
                Drawing.sha256_hash == sha256_hash,
                Drawing.project_id == project_id,
                Drawing.is_deleted == False,
            )
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Structural sanity check dispatcher
# ---------------------------------------------------------------------------


def _run_sanity_check(filepath: str, file_type: str) -> str:
    """Run the structural sanity check appropriate for *file_type*.

    Returns a ``routing_hint`` string:
        - ``"cad_parser"`` — vector content found, route to CAD parser.
        - ``"ai_vision"`` — no vector content (scanned image), route to AI.
        - ``"image"`` — image file, no structural check needed.
        - ``"unknown"`` — couldn't determine format.

    Logs warnings when a file fails the sanity check, but does **not**
    reject the upload — the file is still stored; only the routing path
    changes.
    """
    if file_type == "pdf":
        is_valid, reason = check_pdf_has_content(filepath)
        if is_valid:
            logger.info("PDF sanity check passed: %s", reason)
            return "cad_parser"
        else:
            logger.warning(
                "PDF sanity check — no vector content, routing to AI vision: %s",
                reason,
            )
            return "ai_vision"

    if file_type == "dxf":
        is_valid, reason = check_dxf_has_content(filepath)
        if is_valid:
            logger.info("DXF sanity check passed: %s", reason)
            return "cad_parser"
        else:
            logger.warning(
                "DXF sanity check failed — routing to AI vision: %s",
                reason,
            )
            return "ai_vision"

    if file_type == "dwg":
        is_valid, reason = check_dwg_has_content(filepath)
        if is_valid:
            logger.info("DWG sanity check passed: %s", reason)
            return "cad_parser"
        else:
            logger.warning(
                "DWG sanity check failed — routing to AI vision: %s",
                reason,
            )
            return "ai_vision"

    # Images — no structural check needed
    if file_type in ("png", "jpg", "jpeg", "webp"):
        return "image"

    return "unknown"


# ---------------------------------------------------------------------------
# Status & object retrieval (unchanged from original)
# ---------------------------------------------------------------------------


async def get_drawing_status(drawing_id: int) -> DrawingStatusResponse:
    """Return the current processing status for a drawing."""
    async with async_session() as db:
        result = await db.execute(
            select(Drawing).where(
                Drawing.id == drawing_id,
                Drawing.is_deleted == False,
            )
        )
        drawing = result.scalar_one_or_none()

    if drawing is None:
        raise HTTPException(
            status_code=404,
            detail=f"Drawing {drawing_id} not found",
        )

    # Count non-deleted detected objects for this drawing
    async with async_session() as db:
        count_result = await db.execute(
            select(DetectedObject.id).where(
                DetectedObject.drawing_id == drawing_id,
                DetectedObject.is_deleted == False,
            )
        )
        object_count = len(count_result.all())

    return DrawingStatusResponse(
        drawing_id=drawing.id,
        filename=drawing.filename,
        status=drawing.status,
        object_count=object_count,
        error_message=drawing.error_message,
        created_at=drawing.created_at,
        processed_at=drawing.processed_at,
    )


async def get_drawing_objects(drawing_id: int) -> list[DrawingObjectResponse]:
    """Return all detected objects for a drawing.

    Each ``DetectedObject`` row is mapped to the ``DrawingObjectResponse``
    schema.  Because the DB model stores ``bbox_coords`` as a JSON string
    and the response expects a ``List[float]``, we parse it here.
    """
    async with async_session() as db:
        result = await db.execute(
            select(DetectedObject).where(
                DetectedObject.drawing_id == drawing_id,
                DetectedObject.is_deleted == False,
            ).order_by(DetectedObject.id)
        )
        objects = list(result.scalars().all())

    return [_map_detected_object(o) for o in objects]


def _map_detected_object(obj: DetectedObject) -> DrawingObjectResponse:
    """Map a SQLAlchemy ``DetectedObject`` instance to the Pydantic response.

    Handles string-to-list conversion for ``bbox_coords``.
    The model does not have dedicated ``location_x``/``location_y`` columns,
    so we derive them from ``bbox_coords`` when available.
    """
    bbox_list = None
    if obj.bbox_coords:
        try:
            import json

            parsed = json.loads(obj.bbox_coords)
            if isinstance(parsed, list) and len(parsed) >= 2:
                bbox_list = [float(v) for v in parsed]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Derive location from bbox centre if possible
    location_x = None
    location_y = None
    if bbox_list and len(bbox_list) >= 4:
        location_x = (bbox_list[0] + bbox_list[2]) / 2.0
        location_y = (bbox_list[1] + bbox_list[3]) / 2.0

    return DrawingObjectResponse(
        id=obj.id,
        drawing_id=obj.drawing_id,
        object_type=obj.object_type,
        label=obj.label,
        length=obj.length,
        width=obj.width,
        area=obj.area,
        height=obj.height,
        thickness=obj.thickness,
        location_x=location_x,
        location_y=location_y,
        layer=obj.layer,
        confidence=obj.confidence,
        bbox_coords=bbox_list,
    )
