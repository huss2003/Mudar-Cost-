"""Proposal generation API endpoint."""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.core import Project
from app.models.detection import BOQItem, DetectedObject
from app.models.reference import Material, Vendor
from app.services.proposal_service import generate_proposal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["proposals"])


@router.post("/{project_id}/proposal")
async def generate_project_proposal(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate a branded Jasfo proposal PDF for the project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Get all BOQ items
    stmt = select(BOQItem).where(
        BOQItem.project_id == project_id,
        BOQItem.is_deleted == False,
    ).order_by(BOQItem.category, BOQItem.id)
    result = await db.execute(stmt)
    all_items = result.scalars().all()

    if not all_items:
        raise HTTPException(400, "No BOQ items found — compute quantities first")

    # Group by trade
    trade_map: dict[str, list] = {}
    for item in all_items:
        trade = item.category or "Other"
        if trade not in trade_map:
            trade_map[trade] = []
        trade_map[trade].append({
            "description": item.description,
            "quantity": item.total_qty or item.quantity or 0,
            "unit": item.unit or "nos",
            "rate": item.rate or 0,
            "total": item.total or 0,
        })

    trades = [
        {"trade": trade, "items": items}
        for trade, items in trade_map.items()
    ]

    # Get materials info
    stmt = (
        select(Material, Vendor)
        .join(Vendor, Material.vendor_id == Vendor.id, isouter=True)
        .limit(20)
    )
    result = await db.execute(stmt)
    mat_rows = result.all()
    materials = [
        {
            "name": m.name,
            "brand": m.brand,
            "quantity": 0,
            "unit": m.unit or "nos",
        }
        for m, v in mat_rows
    ]

    # Detected objects count
    stmt = select(DetectedObject).where(
        DetectedObject.drawing_id.in_(
            select(DetectedObject.drawing_id).where(
                DetectedObject.id.in_(
                    select(BOQItem.source_object_id).where(
                        BOQItem.project_id == project_id,
                        BOQItem.source_object_id.is_not(None),
                    )
                )
            )
        )
    )
    result = await db.execute(stmt)
    obj_count = len(result.scalars().all())

    # Terms
    terms = [
        "All rates are exclusive of GST unless otherwise stated.",
        "The scope includes all items listed in the BOQ. Any additional work will be billed separately.",
        "Material selections are as per the approved material schedule attached.",
        "Site conditions affecting the scope must be communicated before commencement.",
        "Payment: 50% advance, 40% on milestone completion, 10% on project handover.",
        "Defects liability period: 12 months from handover.",
        "This proposal is valid for 15 days from issuance.",
        "Force majeure clauses apply as per standard industry practice.",
    ]

    pdf_bytes = generate_proposal(
        project_name=project.name or f"Project {project_id}",
        project_client=project.client_name or "",
        project_location=project.location or "",
        proposal_number=f"JDF-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        total_area=sum(
            (item.total_qty or item.quantity or 0) for item in all_items
            if item.unit in ("sqm", "m²")
        ),
        total_cost=sum(item.total or 0 for item in all_items),
        estimated_duration=max(len(trades) * 15, 30),
        trades=trades,
        materials=materials,
        terms=terms,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="Proposal_{project_id}.pdf"',
        },
    )

