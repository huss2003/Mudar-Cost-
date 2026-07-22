"""AI-enhanced detection pipeline: rasterize → MiMo detect → merge with rule-based.

Usage
-----
    result = await enhance_detection(drawing_id, minio_object_key, file_type)

The pipeline:
  1. Downloads the drawing from MinIO to a temp file.
  2. Rasterizes the drawing (DXF/PDF → PNG) at 150 DPI.
  3. Runs the MiMo vision model on each PNG page.
  4. Loads existing rule-based (CAD/PDF) objects from the DB.
  5. Merges rule-based + AI objects via :func:`merge_strategy.merge_objects`.
  6. Soft-deletes old objects and writes the merged set.
  7. Returns a summary dict.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.minio_client import get_minio_client
from app.models.core import Drawing
from app.models.detection import DetectedObject
from app.schemas.detection import DetectedObjectCreate, DetectionResult

from app.ai.detection_cache import (
    cache_result,
    compute_sha256,
    get_cached_result,
    rebuild_detection_from_cache,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — modules are resolved at first call so this file can be
# imported even when optional dependencies aren't installed yet.
# ---------------------------------------------------------------------------

_MIMO_CLIENT: Any = None
_RASTERIZER: Any = None
_NORMALIZER: Any = None
_MERGE_FN: Any = None


def _get_mimo_client():
    global _MIMO_CLIENT
    if _MIMO_CLIENT is None:
        try:
            from app.ai.mimo_client import MimoVisionClient

            _MIMO_CLIENT = MimoVisionClient()
        except (ImportError, Exception) as exc:
            logger.warning("MimoVisionClient not available: %s", exc)
            _MIMO_CLIENT = None  # type: ignore[assignment]
    return _MIMO_CLIENT


def _get_rasterizer():
    global _RASTERIZER
    if _RASTERIZER is None:
        try:
            from app.ai.rasterizer import rasterize_drawing as _r

            _RASTERIZER = _r
        except (ImportError, AttributeError) as exc:
            logger.warning("Rasterizer not available: %s", exc)
            _RASTERIZER = None
    return _RASTERIZER


def _get_normalizer():
    global _NORMALIZER
    if _NORMALIZER is None:
        try:
            from app.services.normalizer import normalize_and_store as _n

            _NORMALIZER = _n
        except (ImportError, AttributeError) as exc:
            logger.warning("Normalizer not available: %s", exc)
            _NORMALIZER = None
    return _NORMALIZER


def _get_merge_fn():
    global _MERGE_FN
    if _MERGE_FN is None:
        try:
            from app.ai.merge_strategy import merge_objects as _m

            _MERGE_FN = _m
        except (ImportError, AttributeError) as exc:
            logger.warning("merge_objects not available: %s", exc)
            _MERGE_FN = None
    return _MERGE_FN


# ---------------------------------------------------------------------------
# CAD-specific prompt passed to the MiMo vision model
# ---------------------------------------------------------------------------

CAD_PROMPT = (
    "You are analyzing an architectural floor plan. Identify and return bounding "
    "boxes for: walls, partitions, doors, windows, columns, beams, stairs, "
    "furniture, rooms, cabinets, plumbing fixtures, electrical symbols, HVAC "
    "symbols, ducts, pipes, and any structural elements. For each object, "
    "provide the type, confidence score, and tight bounding box coordinates."
)


# ---------------------------------------------------------------------------
# DB ↔ schema conversion helpers
# ---------------------------------------------------------------------------


def _obj_from_db(detected: DetectedObject) -> DetectedObjectCreate:
    """Convert a ``DetectedObject`` ORM row back to a ``DetectedObjectCreate``.

    The ORM model stores ``bbox_coords`` as a comma-separated string;
    we parse it back to a float list for the Pydantic schema.
    """
    bbox: Optional[List[float]] = None
    if detected.bbox_coords:
        try:
            parts = [float(x.strip()) for x in detected.bbox_coords.split(",")]
            if len(parts) == 4:
                bbox = parts
        except (ValueError, TypeError):
            pass

    raw_attrs: dict[str, Any] = {}
    if detected.metadata_json:
        try:
            raw_attrs = (
                json.loads(detected.metadata_json)
                if isinstance(detected.metadata_json, str)
                else detected.metadata_json
            )
        except (json.JSONDecodeError, TypeError):
            raw_attrs = {}

    polyline: Optional[List[dict[str, Any]]] = None
    if detected.polyline_json:
        try:
            polyline = (
                json.loads(detected.polyline_json)
                if isinstance(detected.polyline_json, str)
                else detected.polyline_json
            )
        except (json.JSONDecodeError, TypeError):
            pass

    return DetectedObjectCreate(
        object_type=detected.object_type,
        label=detected.label,
        length=detected.length,
        width=detected.width,
        area=detected.area,
        height=detected.height,
        thickness=detected.thickness,
        layer=detected.layer,
        confidence=detected.confidence or 1.0,
        source=raw_attrs.get("source", "cad"),
        bbox_coords=bbox,
        polyline_json=polyline,
        raw_attributes=raw_attrs,
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


async def enhance_detection(
    drawing_id: int,
    minio_object_key: str,
    file_type: str,
    trace_id: str | None = None,
) -> dict:
    """Run the full AI enhancement pipeline for a single drawing.

    Parameters
    ----------
    drawing_id : int
        Primary key of the ``Drawing`` record in Postgres.
    minio_object_key : str
        MinIO object key for the uploaded drawing file.
    file_type : str
        File extension (``"dxf"``, ``"dwg"``, ``"pdf"``).

    Returns
    -------
    dict
        Summary including ``status``, ``object_count``, ``ai_object_count``,
        ``merged_count``, ``cost``, and ``processing_time_ms``.
    """
    start_time = time.time()
    local_path: Optional[str] = None
    png_paths: List[str] = []

    result_summary: dict = {
        "drawing_id": drawing_id,
        "status": "failed",
        "object_count": 0,
        "ai_object_count": 0,
        "merged_count": 0,
        "cost": 0.0,
        "error": None,
    }

    async with async_session() as db:
        try:
            # ──────────────────────────────────────────────────────────────
            # 1. Fetch drawing & validate
            # ──────────────────────────────────────────────────────────────
            drawing = await db.get(Drawing, drawing_id)
            if drawing is None:
                raise ValueError(f"Drawing {drawing_id} not found in database")

            logger.info(
                "Starting AI enhancement for drawing %s (minio=%s, type=%s)",
                drawing_id,
                minio_object_key,
                file_type,
            )
            drawing.status = "processing"
            drawing.error_message = None
            await db.commit()

            # ──────────────────────────────────────────────────────────────
            # 2. Download file from MinIO
            # ──────────────────────────────────────────────────────────────
            temp_dir = Path(tempfile.gettempdir()) / "auto-cost-drawings"
            temp_dir.mkdir(parents=True, exist_ok=True)
            local_path = str(temp_dir / f"{uuid.uuid4().hex}_{drawing.filename}")

            mc = get_minio_client()
            mc.fget_object(settings.MINIO_BUCKET, minio_object_key, local_path)
            logger.info(
                "Downloaded %s → %s (%d bytes)",
                minio_object_key,
                local_path,
                os.path.getsize(local_path),
            )

            # ──────────────────────────────────────────────────────────────
            # 3. Run AI detection: sha256 cache check → rasterize → MiMo
            # ──────────────────────────────────────────────────────────────
            ai_objects: List[DetectedObjectCreate] = []
            rasterizer = _get_rasterizer()
            mimo = _get_mimo_client()
            png_paths: List[str] = []

            # Compute sha256 of the uploaded file for caching
            try:
                with open(local_path, "rb") as _f:
                    file_bytes = _f.read()
                file_sha256 = compute_sha256(file_bytes)
                logger.info(
                    "File sha256=%s for drawing %s",
                    file_sha256[:16],
                    drawing_id,
                )
            except OSError as exc:
                logger.warning(
                    "Could not compute sha256 for %s: %s — proceeding without cache",
                    local_path,
                    exc,
                )
                file_sha256 = None

            # Try cache first
            cache_hit = False
            if file_sha256 is not None:
                cached = get_cached_result(file_sha256)
                if cached is not None:
                    cached_dr = rebuild_detection_from_cache(cached)
                    if cached_dr is not None and cached_dr.objects:
                        for obj in cached_dr.objects:
                            obj.source = "ai"
                            obj.is_ai_generated = True
                            obj.ai_status = "available"
                            ai_objects.append(obj)
                        cache_hit = True
                        logger.info(
                            "Cache HIT — re-using %d cached AI objects for sha256=%s",
                            len(ai_objects),
                            file_sha256[:16],
                        )

            if not cache_hit:
                if rasterizer is None or mimo is None:
                    ai_unavailable_reason = (
                        "rasterizer unavailable" if rasterizer is None else ""
                    )
                    if mimo is None:
                        ai_unavailable_reason = (
                            "MiMo client unavailable" if not ai_unavailable_reason
                            else f"{ai_unavailable_reason}, MiMo client unavailable"
                        )
                    logger.warning(
                        "AI detection modules unavailable (%s) — skipping AI detection "
                        "[trace_id=%s]",
                        ai_unavailable_reason,
                        trace_id or "none",
                    )
                else:
                    png_paths = rasterizer(local_path, dpi=150)

                    if not png_paths:
                        logger.warning(
                            "Rasterizer returned no PNG pages for %s", local_path
                        )
                    else:
                        logger.info(
                            "Rasterized %s → %d PNG pages",
                            local_path,
                            len(png_paths),
                        )

                        combined_page_objects: List[DetectedObjectCreate] = []
                        for page_idx, png_path in enumerate(png_paths):
                            try:
                                page_result = mimo.detect_objects(
                                    image_path=png_path,
                                    prompt=CAD_PROMPT,
                                )
                                # Tag every AI object
                                for obj in page_result.objects:
                                    obj.source = "ai"
                                    obj.is_ai_generated = True
                                    obj.ai_status = "available"
                                    combined_page_objects.append(obj)
                                logger.info(
                                    "Page %d/%d: detected %d objects",
                                    page_idx + 1,
                                    len(png_paths),
                                    len(page_result.objects),
                                )
                            except Exception as exc:
                                logger.warning(
                                    "MiMo detection failed on page %d (%s): %s "
                                    "[trace_id=%s]",
                                    page_idx + 1,
                                    png_path,
                                    exc,
                                    trace_id or "none",
                                )

                        ai_objects = combined_page_objects

                        # Cache the combined result, but only if at least one page
                        # completed successfully (status == "completed").
                        if file_sha256 is not None and combined_page_objects:
                            combined_dr = DetectionResult(
                                drawing_id=drawing_id,
                                status="completed",
                                objects=combined_page_objects,
                                errors=[],
                                source_format=file_type,
                            )
                            cache_result(
                                sha256_digest=file_sha256,
                                mimo_raw={},
                                detection_result=combined_dr,
                            )

            ai_object_count = len(ai_objects)
            logger.info(
                "AI detection complete: %d objects%s",
                ai_object_count,
                f" (cache hit)" if cache_hit else f" across {len(png_paths)} pages",
            )

            # ──────────────────────────────────────────────────────────────
            # 4. Load existing rule-based objects from DB
            # ──────────────────────────────────────────────────────────────
            stmt = (
                select(DetectedObject)
                .where(
                    DetectedObject.drawing_id == drawing_id,
                    DetectedObject.is_deleted == False,
                )
                .order_by(DetectedObject.id)
            )
            existing_rows = (await db.execute(stmt)).scalars().all()
            rule_objects = [_obj_from_db(row) for row in existing_rows]
            logger.info(
                "Loaded %d existing rule-based objects for drawing %s",
                len(rule_objects),
                drawing_id,
            )

            # ──────────────────────────────────────────────────────────────
            # 5. Merge rule-based + AI objects
            # ──────────────────────────────────────────────────────────────
            merge_fn = _get_merge_fn()
            if merge_fn is None:
                raise RuntimeError(
                    "merge_strategy.merge_objects is not available — "
                    "cannot merge detection results"
                )

            merged = merge_fn(rule_objects, ai_objects)
            merged_count = len(merged)
            logger.info(
                "Merge complete: %d rule + %d AI → %d merged objects",
                len(rule_objects),
                ai_object_count,
                merged_count,
            )

            # ──────────────────────────────────────────────────────────────
            # 6. Write merged objects: soft-delete old, write new
            # ──────────────────────────────────────────────────────────────
            for row in existing_rows:
                row.is_deleted = True
                row.deleted_at = datetime.utcnow()

            merged_result = DetectionResult(
                drawing_id=drawing_id,
                status="completed",
                objects=merged,
                errors=[],
                source_format=file_type,
            )

            normalizer = _get_normalizer()
            if normalizer is not None:
                object_count = await normalizer(db, drawing_id, merged_result)
            else:
                object_count = await _write_merged_fallback(db, drawing_id, merged_result)

            # ──────────────────────────────────────────────────────────────
            # 7. Update drawing status
            # ──────────────────────────────────────────────────────────────
            drawing.status = "analyzed"
            drawing.processed_at = datetime.utcnow()
            await db.commit()

            elapsed = time.time() - start_time
            logger.info(
                "AI enhancement for drawing %s complete: %d objects (%.2fs)",
                drawing_id,
                object_count,
                elapsed,
            )

            result_summary.update(
                {
                    "status": "analyzed",
                    "object_count": object_count,
                    "ai_object_count": ai_object_count,
                    "merged_count": merged_count,
                    "cost": 0.0,  # API cost tracking placeholder
                    "processing_time_ms": round(elapsed * 1000, 2),
                }
            )

        except Exception as exc:
            await db.rollback()
            try:
                drawing = await db.get(Drawing, drawing_id)
                if drawing is not None:
                    drawing.status = "failed"
                    drawing.error_message = str(exc)[:1000]
                    await db.commit()
            except Exception as inner:
                logger.error("Failed to update drawing error status: %s", inner)

            logger.exception(
                "AI enhancement failed for drawing %s: %s [trace_id=%s]",
                drawing_id,
                exc,
                trace_id or "none",
            )
            result_summary["error"] = str(exc)[:1000]
            raise

        finally:
            # Clean up temp files
            if local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError as rm_err:
                    logger.warning("Could not remove temp file %s: %s", local_path, rm_err)
            for png in png_paths:
                if os.path.exists(png):
                    try:
                        os.remove(png)
                    except OSError as rm_err:
                        logger.warning(
                            "Could not remove PNG temp file %s: %s",
                            png,
                            rm_err,
                        )

        return result_summary


# ---------------------------------------------------------------------------
# Fallback writer (same pattern as tasks/drawings.py)
# ---------------------------------------------------------------------------


async def _write_merged_fallback(
    db,
    drawing_id: int,
    result: DetectionResult,
) -> int:
    """Write merged objects directly when the normalizer module is unavailable."""
    import json as _json

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
            bbox_coords=(
                ",".join(str(c) for c in obj.bbox_coords)
                if obj.bbox_coords
                else None
            ),
            polyline_json=_json.dumps(obj.polyline_json) if obj.polyline_json else None,
            metadata_json=_json.dumps(obj.raw_attributes) if obj.raw_attributes else None,
        )
        db.add(detected)
        written += 1
    if written:
        await db.commit()
    return written
