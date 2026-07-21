"""
Celery tasks for drawing processing: parse, detect, normalise, store.

Uses structlog for structured JSON logging with trace_id propagation.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from time import monotonic

import structlog
from sqlalchemy import select

from app.celery_app import celery_app
from app.config import settings
from app.database import async_session
from app.minio_client import get_minio_client
from app.models.core import Drawing
from app.models.detection import DetectedObject
from app.schemas.detection import DetectedObjectCreate, DetectionResult
from app.services.metrics import drawings_uploaded, parse_duration
from app.services.trace import get_trace_id, set_trace_id

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Parser imports — stubs for parsers that will be created by other agents.
# We import inside the task body so the task module can load even when
# parsers aren't written yet.
# ---------------------------------------------------------------------------


def _import_dxf_parser():
    """Lazy-import the DXF parser; returns parse_dxf or None."""
    try:
        from app.services.dxf_parser import parse_dxf as _p
        return _p
    except (ImportError, AttributeError) as exc:
        logger.warning("dxf_parser_unavailable", error=str(exc))
        return None


def _import_pdf_parser():
    """Lazy-import the PDF parser; returns parse_pdf or None."""
    try:
        from app.services.pdf_parser import parse_pdf as _p
        return _p
    except (ImportError, AttributeError) as exc:
        logger.warning("pdf_parser_unavailable", error=str(exc))
        return None


def _import_normalizer():
    """Lazy-import the normalizer; returns normalize_and_store or None."""
    try:
        from app.services.normalizer import normalize_and_store as _n
        return _n
    except (ImportError, AttributeError) as exc:
        logger.warning("normalizer_unavailable", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _convert_dxf_result(raw: dict, drawing_id: int) -> DetectionResult:
    """Convert the dict-based DXF parser result to a DetectionResult model."""
    objects = []
    for obj_dict in raw.get("objects", []):
        try:
            objects.append(DetectedObjectCreate(**obj_dict))
        except Exception as exc:
            logger.warning(
                "skipping_malformed_dxf_object",
                object_type=obj_dict.get("object_type"),
                error=str(exc),
            )
    return DetectionResult(
        drawing_id=drawing_id,
        status=raw.get("status", "completed"),
        objects=objects,
        errors=raw.get("errors", []),
        processing_time_ms=raw.get("processing_time_ms"),
        source_format=raw.get("source_format", "dxf"),
    )


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.drawings.process_drawing",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_drawing(
    self,
    drawing_id: int,
    minio_object_key: str,
    file_type: str,
    trace_id: str | None = None,
) -> dict:
    """Process an uploaded drawing: download, parse, normalise, store.

    Runs asynchronously inside the Celery worker.  All DB I/O is
    performed via ``asyncio.run()`` to bridge async SQLAlchemy with
    the sync Celery task context.
    """
    task_start = monotonic()
    task_id = self.request.id

    # Propagate trace_id into this task's context
    set_trace_id(trace_id)
    trace_id_val = get_trace_id()

    logger.info(
        "celery_task_start",
        task_name="app.tasks.drawings.process_drawing",
        task_id=task_id,
        drawing_id=drawing_id,
        file_type=file_type,
        trace_id=trace_id_val,
    )

    async def _run() -> dict:
        local_path: str | None = None
        async with async_session() as db:
            try:
                # -------------------------------------------------------
                # 1. Fetch drawing & update status → 'processing'
                # -------------------------------------------------------
                drawing = await db.get(Drawing, drawing_id)
                if drawing is None:
                    msg = f"Drawing {drawing_id} not found in database"
                    logger.error("drawing_not_found", drawing_id=drawing_id)
                    return {"task_id": task_id, "drawing_id": drawing_id, "status": "failed", "error": msg}

                drawing.status = "processing"
                drawing.error_message = None
                await db.commit()
                logger.info("drawing_status_processing", drawing_id=drawing_id, task_id=task_id)

                # -------------------------------------------------------
                # 2. Download file from MinIO
                # -------------------------------------------------------
                temp_dir = Path(tempfile.gettempdir()) / "auto-cost-drawings"
                temp_dir.mkdir(parents=True, exist_ok=True)
                local_path = str(temp_dir / f"{uuid.uuid4().hex}_{drawing.filename}")

                mc = get_minio_client()
                mc.fget_object(settings.MINIO_BUCKET, minio_object_key, local_path)
                file_bytes = os.path.getsize(local_path)
                logger.info(
                    "file_downloaded",
                    minio_key=minio_object_key,
                    local_path=local_path,
                    bytes=file_bytes,
                )

                # -------------------------------------------------------
                # 3. Parse the file
                # -------------------------------------------------------
                parse_start = monotonic()
                file_type_lower = file_type.lower()

                if file_type_lower == "dxf":
                    parser = _import_dxf_parser()
                    if parser is None:
                        raise RuntimeError("DXF parser is not available — cannot process .dxf files")
                    raw = parser(local_path, drawing_id)
                    result = _convert_dxf_result(raw, drawing_id)

                elif file_type_lower == "dwg":
                    logger.warning(
                        "dwg_unsupported",
                        drawing_id=drawing_id,
                    )
                    result = DetectionResult(
                        drawing_id=drawing_id,
                        status="completed_with_errors",
                        objects=[],
                        errors=["DWG format requires LibreDWG conversion — not yet implemented"],
                        source_format="dwg",
                    )

                elif file_type_lower == "pdf":
                    parser = _import_pdf_parser()
                    if parser is None:
                        raise RuntimeError("PDF parser is not available — cannot process .pdf files")
                    result = parser(local_path, drawing_id)

                else:
                    raise ValueError(f"Unsupported file type: {file_type}")

                parse_duration_s = (monotonic() - parse_start)
                parse_duration.labels(file_type=file_type_lower).observe(parse_duration_s)

                # -------------------------------------------------------
                # 4. Normalise & store detected objects
                # -------------------------------------------------------
                normalizer = _import_normalizer()
                if normalizer is not None:
                    object_count = await normalizer(db, drawing_id, result)
                else:
                    # Fallback: write objects directly when no normalizer
                    object_count = await _write_objects_fallback(db, drawing_id, result)

                logger.info(
                    "parse_complete",
                    drawing_id=drawing_id,
                    objects=len(result.objects),
                    errors=len(result.errors),
                    duration_s=round(parse_duration_s, 3),
                )

                # -------------------------------------------------------
                # 5. Update drawing status → 'analyzed'
                # -------------------------------------------------------
                drawing.status = "analyzed"
                drawing.processed_at = datetime.utcnow()
                if result.errors:
                    drawing.error_message = "; ".join(result.errors[:5])
                await db.commit()

                # Record metrics
                drawings_uploaded.labels(
                    file_type=file_type_lower,
                    status="success",
                ).inc()

                duration_ms = (monotonic() - task_start) * 1000
                logger.info(
                    "celery_task_finish",
                    task_name="app.tasks.drawings.process_drawing",
                    task_id=task_id,
                    drawing_id=drawing_id,
                    duration_ms=round(duration_ms, 1),
                    object_count=object_count,
                    trace_id=trace_id_val,
                )
                return {
                    "task_id": task_id,
                    "drawing_id": drawing_id,
                    "status": "analyzed",
                    "object_count": object_count,
                    "processing_time_ms": result.processing_time_ms,
                }

            except Exception as exc:
                await db.rollback()
                try:
                    drawing = await db.get(Drawing, drawing_id)
                    if drawing:
                        drawing.status = "failed"
                        drawing.error_message = str(exc)[:1000]
                        await db.commit()
                except Exception as inner:
                    logger.error("drawing_error_status_failed", error=str(inner))

                drawings_uploaded.labels(
                    file_type=file_type.lower(),
                    status="failed",
                ).inc()

                logger.error(
                    "celery_task_failure",
                    task_name="app.tasks.drawings.process_drawing",
                    task_id=task_id,
                    drawing_id=drawing_id,
                    error=str(exc),
                    exc_info=exc,
                )
                # Re-raise so Celery marks the task as FAILURE
                raise

            finally:
                # Clean up temp file
                if local_path and os.path.exists(local_path):
                    try:
                        os.remove(local_path)
                    except OSError as rm_err:
                        logger.warning("temp_file_cleanup_failed", path=local_path, error=str(rm_err))

    # Run the async pipeline
    return asyncio.run(_run())


async def _write_objects_fallback(
    db,
    drawing_id: int,
    result: DetectionResult,
) -> int:
    """Fallback object-writer when the normalizer module is not available.

    Directly writes each DetectionResult object as a DetectedObject row.
    """
    written = 0
    for obj in result.objects:
        detected = DetectedObject(
            drawing_id=drawing_id,
            object_type=obj.object_type,
            label=obj.label,
            length=obj.length,
            width=obj.width,
            area=obj.area,
            height=obj.height,
            thickness=obj.thickness,
            layer=obj.layer,
            confidence=obj.confidence,
            bbox_coords=json.dumps(obj.bbox_coords) if obj.bbox_coords else None,
            polyline_json=json.dumps(obj.polyline_json) if obj.polyline_json else None,
            metadata_json=json.dumps(obj.raw_attributes) if obj.raw_attributes else None,
        )
        db.add(detected)
        written += 1
    if written:
        await db.commit()
    return written
