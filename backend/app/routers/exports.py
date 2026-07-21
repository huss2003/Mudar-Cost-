"""
Export API endpoints.

Provides async document generation (BOQ Excel, Proposal PDF, Purchase List,
Client Presentation) with Celery-based background processing.

Endpoints
---------
- POST /projects/{project_id}/export?format=xlsx|pdf|proposal_pdf|boq_xlsx
- POST /projects/{project_id}/purchase-list
- POST /projects/{project_id}/client-presentation
- GET  /exports/{export_id}/download
- GET  /exports — list exports for a project
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.celery_app import celery_app
from app.database import async_session
from app.minio_client import get_minio_client
from app.models.core import Project
from app.models.history import ExportRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exports", tags=["exports"])

# ---------------------------------------------------------------------------
# POST /projects/{project_id}/export
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/export", status_code=202)
async def create_export(
    project_id: int,
    format: str = Query("xlsx", description="Export format: xlsx, pdf, proposal_pdf, boq_xlsx"),
) -> dict:
    """Dispatch a Celery task to generate an export document.

    Supported formats:
    - ``boq_xlsx`` / ``xlsx`` — Multi-sheet BOQ Excel workbook
    - ``proposal_pdf`` / ``pdf`` — Full proposal PDF
    - ``purchase_list`` — Purchase list Excel (use /purchase-list endpoint)
    - ``client_presentation`` — Client presentation PDF (use /client-presentation endpoint)
    """
    # Normalise format aliases
    format_map = {
        "xlsx": "boq_xlsx",
        "boq_xlsx": "boq_xlsx",
        "pdf": "proposal_pdf",
        "proposal_pdf": "proposal_pdf",
        "purchase_list": "purchase_list",
        "client_presentation": "client_presentation",
    }

    export_type = format_map.get(format.lower())
    if export_type is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{format}'. Valid: {', '.join(sorted(format_map))}",
        )

    # Verify project exists
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
                status_code=404, detail=f"Project {project_id} not found"
            )

    # Dispatch Celery task
    task = celery_app.send_task(
        "app.tasks.exports.generate_export",
        args=[project_id, export_type],
    )
    logger.info(
        "Dispatched export task %s for project %d type=%s",
        task.id, project_id, export_type,
    )

    return {
        "job_id": task.id,
        "project_id": project_id,
        "export_type": export_type,
        "status": "processing",
        "message": f"Export task dispatched. Use GET /exports to poll for completion.",
    }


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/purchase-list
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/purchase-list", status_code=202)
async def create_purchase_list(project_id: int) -> dict:
    """Dispatch a Celery task to generate a purchase list Excel."""
    async with async_session() as db:
        result = await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.is_deleted == False,  # noqa: E712
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=404, detail=f"Project {project_id} not found"
            )

    task = celery_app.send_task(
        "app.tasks.exports.generate_export",
        args=[project_id, "purchase_list"],
    )
    logger.info("Dispatched purchase-list task %s for project %d", task.id, project_id)

    return {
        "job_id": task.id,
        "project_id": project_id,
        "export_type": "purchase_list",
        "status": "processing",
    }


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/client-presentation
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/client-presentation", status_code=202)
async def create_client_presentation(project_id: int) -> dict:
    """Dispatch a Celery task to generate a client presentation PDF."""
    async with async_session() as db:
        result = await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.is_deleted == False,  # noqa: E712
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=404, detail=f"Project {project_id} not found"
            )

    task = celery_app.send_task(
        "app.tasks.exports.generate_export",
        args=[project_id, "client_presentation"],
    )
    logger.info("Dispatched client-presentation task %s for project %d", task.id, project_id)

    return {
        "job_id": task.id,
        "project_id": project_id,
        "export_type": "client_presentation",
        "status": "processing",
    }


# ---------------------------------------------------------------------------
# GET /exports — list exports for a project
# ---------------------------------------------------------------------------


@router.get("")
async def list_exports(
    project_id: int = Query(..., description="Filter by project ID"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """List export records for a project, newest first."""
    async with async_session() as db:
        stmt = (
            select(ExportRecord)
            .where(ExportRecord.project_id == project_id)
            .order_by(ExportRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(stmt)
        records = result.scalars().all()

        # Also get total count
        count_stmt = (
            select(ExportRecord.id)
            .where(ExportRecord.project_id == project_id)
        )
        count_result = await db.execute(count_stmt)
        total = len(count_result.all())

    return {
        "project_id": project_id,
        "total": total,
        "offset": offset,
        "limit": limit,
        "exports": [
            {
                "id": r.id,
                "export_type": r.export_type,
                "status": r.status,
                "filename": r.filename,
                "file_size": r.file_size,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in records
        ],
    }


# ---------------------------------------------------------------------------
# GET /exports/{export_id}/download
# ---------------------------------------------------------------------------


@router.get("/{export_id}/download")
async def download_export(export_id: int) -> dict:
    """Return a signed MinIO URL to download the generated export file.

    The URL is valid for 1 hour. The caller must apply appropriate
    authentication before returning this URL to the client.
    """
    async with async_session() as db:
        record = await db.get(ExportRecord, export_id)
        if record is None:
            raise HTTPException(
                status_code=404, detail=f"Export record {export_id} not found"
            )
        if record.status != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Export {export_id} status is '{record.status}', not 'completed'",
            )
        if not record.minio_key:
            raise HTTPException(
                status_code=500,
                detail=f"Export {export_id} has no MinIO key (generation may have failed)",
            )

    # Generate a presigned URL (valid 1 hour)
    try:
        client = get_minio_client()
        url = client.get_presigned_url(
            method="GET",
            bucket_name="exports",
            object_name=record.minio_key,
            expires=3600,
        )
    except Exception as exc:
        logger.exception("Failed to generate presigned URL for export %d", export_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate download URL: {exc}",
        )

    return {
        "export_id": export_id,
        "filename": record.filename,
        "file_size": record.file_size,
        "content_type": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if record.filename and record.filename.endswith(".xlsx")
            else "application/pdf"
        ),
        "url": url,
        "expires_in_seconds": 3600,
    }
