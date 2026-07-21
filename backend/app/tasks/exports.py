"""
Celery tasks for async export generation.

Generates documents (XLSX, PDF) via the export service, uploads to MinIO,
and records the result in the ExportRecord table.

Uses structlog for structured JSON logging with trace_id propagation.
"""
from __future__ import annotations

import asyncio
import io
import uuid
from datetime import datetime, timezone
from time import monotonic

import structlog
from celery import Task
from sqlalchemy import select

from app.celery_app import celery_app
from app.database import async_session
from app.minio_client import get_minio_client
from app.models.core import Project
from app.models.history import ExportRecord
from app.services.export_service import (
    export_boq_xlsx,
    export_proposal_pdf,
    export_purchase_list,
    export_client_presentation,
)
from app.services.trace import get_trace_id, set_trace_id

logger = structlog.get_logger(__name__)

EXPORT_FORMAT_MAP = {
    "xlsx": export_boq_xlsx,
    "boq_xlsx": export_boq_xlsx,
    "pdf": export_proposal_pdf,
    "proposal_pdf": export_proposal_pdf,
    "purchase_list": export_purchase_list,
    "client_presentation": export_client_presentation,
}


@celery_app.task(
    name="app.tasks.exports.generate_export",
    bind=True,
    track_started=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def generate_export(
    self: Task,
    project_id: int,
    export_type: str,
    export_settings: dict | None = None,
    trace_id: str | None = None,
) -> dict:
    """Celery task: generate an export document and upload to MinIO.

    Parameters
    ----------
    project_id:
        Project ID to export.
    export_type:
        One of: ``boq_xlsx``, ``proposal_pdf``, ``purchase_list``,
        ``client_presentation``.
    export_settings:
        Optional dict of export settings (e.g. ``{"language": "en"}``).
    trace_id:
        Trace ID propagated from the HTTP request that triggered this task.

    Returns
    -------
    dict
        ``{"export_id": int, "status": str, "minio_key": str, "filename": str}``
    """
    task_start = monotonic()
    task_id = self.request.id

    # Propagate trace_id
    set_trace_id(trace_id)
    trace_id_val = get_trace_id()

    logger.info(
        "celery_task_start",
        task_name="app.tasks.exports.generate_export",
        task_id=task_id,
        project_id=project_id,
        export_type=export_type,
        trace_id=trace_id_val,
    )

    # Resolve the export factory
    export_fn = EXPORT_FORMAT_MAP.get(export_type)
    if export_fn is None:
        raise ValueError(
            f"Unknown export_type={export_type!r}. "
            f"Valid: {', '.join(sorted(EXPORT_FORMAT_MAP))}",
        )

    # Build the MinIO object key prefix
    safe_type = export_type.replace("_", "-")
    object_key = f"exports/{project_id}/{safe_type}/{uuid.uuid4().hex[:12]}"

    export_record_id: int | None = None
    export_filename: str = ""

    try:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)

            async def _generate() -> tuple[bytes, str]:
                async with async_session() as db:
                    # Verify project exists
                    result = await db.execute(
                        select(Project).where(
                            Project.id == project_id,
                            Project.is_deleted == False,  # noqa: E712
                        )
                    )
                    project = result.scalar_one_or_none()
                    if project is None:
                        raise ValueError(f"Project {project_id} not found")

                    # Create export record (pending → processing)
                    record = ExportRecord(
                        project_id=project_id,
                        export_type=export_type,
                        status="processing",
                    )
                    db.add(record)
                    await db.flush()
                    nonlocal export_record_id
                    export_record_id = record.id

                    # Generate the document
                    data_bytes, filename = await export_fn(project_id, db)
                    nonlocal export_filename
                    export_filename = filename

                    # Upload to MinIO
                    minio_client = get_minio_client()
                    bucket = "exports"
                    # Ensure bucket exists
                    if not minio_client.bucket_exists(bucket):
                        minio_client.make_bucket(bucket)

                    minio_client.put_object(
                        bucket_name=bucket,
                        object_name=object_key,
                        data=io.BytesIO(data_bytes),
                        length=len(data_bytes),
                        content_type=(
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            if filename.endswith(".xlsx")
                            else "application/pdf"
                        ),
                    )

                    # Update the record
                    record.status = "completed"
                    record.minio_key = object_key
                    record.filename = filename
                    record.file_size = len(data_bytes)
                    record.completed_at = datetime.now(timezone.utc)
                    await db.flush()

                    return data_bytes, filename

            loop.run_until_complete(_generate())
        finally:
            loop.close()

        duration_ms = (monotonic() - task_start) * 1000
        logger.info(
            "celery_task_finish",
            task_name="app.tasks.exports.generate_export",
            task_id=task_id,
            project_id=project_id,
            export_type=export_type,
            duration_ms=round(duration_ms, 1),
            trace_id=trace_id_val,
        )

        return {
            "export_id": export_record_id,
            "status": "completed",
            "minio_key": object_key,
            "filename": export_filename,
        }

    except Exception as exc:
        logger.error(
            "celery_task_failure",
            task_name="app.tasks.exports.generate_export",
            task_id=task_id,
            project_id=project_id,
            export_type=export_type,
            error=str(exc),
            exc_info=exc,
        )

        # Update the export record to failed
        if export_record_id is not None:
            try:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)

                    async def _fail():
                        async with async_session() as db:
                            record = await db.get(ExportRecord, export_record_id)
                            if record:
                                record.status = "failed"
                                record.error_message = str(exc)[:500]
                                await db.flush()

                    loop.run_until_complete(_fail())
                finally:
                    loop.close()
            except Exception:
                logger.exception("failed_to_update_export_record")

        # Retry or re-raise
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


@celery_app.task(
    name="app.tasks.exports.generate_boq_xlsx",
    bind=True,
    track_started=True,
)
def generate_boq_xlsx(self: Task, project_id: int, trace_id: str | None = None) -> dict:
    """Convenience wrapper: generate BOQ Excel export."""
    return generate_export(project_id, "boq_xlsx", trace_id=trace_id)


@celery_app.task(
    name="app.tasks.exports.generate_proposal_pdf",
    bind=True,
    track_started=True,
)
def generate_proposal_pdf(self: Task, project_id: int, trace_id: str | None = None) -> dict:
    """Convenience wrapper: generate Proposal PDF export."""
    return generate_export(project_id, "proposal_pdf", trace_id=trace_id)


@celery_app.task(
    name="app.tasks.exports.generate_purchase_list",
    bind=True,
    track_started=True,
)
def generate_purchase_list(self: Task, project_id: int, trace_id: str | None = None) -> dict:
    """Convenience wrapper: generate Purchase List export."""
    return generate_export(project_id, "purchase_list", trace_id=trace_id)


@celery_app.task(
    name="app.tasks.exports.generate_client_presentation",
    bind=True,
    track_started=True,
)
def generate_client_presentation(self: Task, project_id: int, trace_id: str | None = None) -> dict:
    """Convenience wrapper: generate Client Presentation export."""
    return generate_export(project_id, "client_presentation", trace_id=trace_id)
