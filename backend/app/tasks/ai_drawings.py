"""Celery task for AI-enhanced drawing detection: rasterize → MiMo → merge.

This task is designed to run **after** the rule-based ``process_drawing``
task has completed, providing an AI-powered enhancement pass.
"""

from __future__ import annotations

import asyncio
import logging

from app.celery_app import DeadLetterTask, celery_app

logger = logging.getLogger(__name__)


def _import_enhance():
    """Lazy-import ``enhance_detection`` so the module loads gracefully."""
    try:
        from app.ai.pipeline import enhance_detection as _e

        return _e
    except (ImportError, AttributeError) as exc:
        logger.warning("AI pipeline not available: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.ai_drawings.process_drawing_ai",
    bind=True,
    base=DeadLetterTask,
    max_retries=2,
    default_retry_delay=120,
    acks_late=True,
)
def process_drawing_ai(
    self,
    drawing_id: int,
    minio_object_key: str,
    file_type: str,
) -> dict:
    """Run AI-enhanced detection on an already-processed drawing.

    This task is designed to be called **after** the rule-based
    :func:`app.tasks.drawings.process_drawing` task completes.  It:

    1. Downloads the drawing from MinIO
    2. Rasterizes it to PNG images via :func:`app.ai.rasterizer.rasterize_drawing`
    3. Runs the MiMo vision model on each PNG page
    4. Loads existing rule-based (CAD/PDF) objects from the DB
    5. Merges AI + rule-based objects via :func:`app.ai.merge_strategy.merge_objects`
    6. Soft-deletes old objects and writes the merged result
    7. Updates drawing status to ``"analyzed"``

    Parameters
    ----------
    drawing_id : int
        Primary key of the ``Drawing`` record.
    minio_object_key : str
        MinIO object key for the drawing file.
    file_type : str
        File extension (``"dxf"``, ``"dwg"``, ``"pdf"``).

    Returns
    -------
    dict
        Summary dict with ``task_id``, ``drawing_id``, ``status``,
        ``object_count``, ``ai_object_count``, ``merged_count``, ``cost``,
        and ``processing_time_ms``.
    """
    task_id = self.request.id

    async def _run() -> dict:
        enhance = _import_enhance()
        if enhance is None:
            error_msg = (
                "AI enhancement pipeline is not available — "
                "check that app/ai/pipeline.py and its dependencies exist"
            )
            logger.error(error_msg)
            return {
                "task_id": task_id,
                "drawing_id": drawing_id,
                "status": "failed",
                "error": error_msg,
            }

        try:
            result = await enhance(drawing_id, minio_object_key, file_type)
            result["task_id"] = task_id
            return result
        except Exception as exc:
            logger.exception(
                "AI enhancement failed for drawing %s: %s",
                drawing_id,
                exc,
            )
            return {
                "task_id": task_id,
                "drawing_id": drawing_id,
                "status": "failed",
                "error": str(exc)[:1000],
            }

    return asyncio.run(_run())
