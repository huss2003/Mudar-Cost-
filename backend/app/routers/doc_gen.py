"""Document generation API endpoints — RFQ, Purchase Order, Gantt chart."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.core import Project
from app.models.detection import BOQItem
from app.models.reference import Vendor
from app.models.rules import CompanyStandard, ProductivityRate
from app.services.doc_gen import (
    generate_rfq,
    generate_purchase_order,
    generate_gantt_svg,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/projects/{project_id}/rfq")
async def generate_project_rfq(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate an RFQ PDF grouped by vendor for the project's BOQ items."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Get BOQ items with vendor info
    stmt = (
        select(BOQItem, Vendor)
        .join(Vendor, BOQItem.vendor_id == Vendor.id, isouter=True)
        .where(
            BOQItem.project_id == project_id,
            BOQItem.is_deleted == False,
        )
        .order_by(Vendor.name, BOQItem.description)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Group by vendor
    vendor_groups: dict[str, dict] = {}
    for boq_item, vendor in rows:
        vname = vendor.name if vendor else "Unassigned"
        if vname not in vendor_groups:
            vendor_groups[vname] = {
                "vendor_name": vname,
                "vendor_address": vendor.address if vendor else "",
                "vendor_gst": vendor.gst if vendor else "",
                "items": [],
            }
        vendor_groups[vname]["items"].append({
            "description": boq_item.description,
            "quantity": boq_item.quantity or 0,
            "unit": boq_item.unit or "nos",
            "material_code": boq_item.material_name or "",
        })

    if not vendor_groups:
        raise HTTPException(400, "No BOQ items found for this project")

    # Generate RFQ for each vendor
    pdfs = {}
    for vname, vdata in vendor_groups.items():
        pdf_bytes = generate_rfq(
            vendor_name=vdata["vendor_name"],
            vendor_address=vdata["vendor_address"],
            vendor_gst=vdata["vendor_gst"],
            items=vdata["items"],
            project_name=project.name or f"Project {project_id}",
            project_ref=f"ACE-{project_id}",
        )
        pdfs[vname] = pdf_bytes

    # For now, return the first vendor's RFQ
    first_vendor = list(vendor_groups.keys())[0]
    return Response(
        content=pdfs[first_vendor],
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="RFQ_{first_vendor}_{project_id}.pdf"',
        },
    )


@router.post("/projects/{project_id}/purchase-order/{vendor_id}")
async def generate_project_po(
    project_id: int,
    vendor_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate a Purchase Order PDF for a specific vendor's items."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(404, "Vendor not found")

    stmt = select(BOQItem).where(
        BOQItem.project_id == project_id,
        BOQItem.vendor_id == vendor_id,
        BOQItem.is_deleted == False,
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    if not items:
        raise HTTPException(400, f"No BOQ items found for vendor {vendor.name}")

    item_data = []
    for item in items:
        qty = item.total_qty or item.quantity or 0
        rate = item.rate or 0
        item_data.append({
            "description": item.description,
            "quantity": qty,
            "unit": item.unit or "nos",
            "rate": rate,
            "amount": qty * rate,
        })

    pdf_bytes = generate_purchase_order(
        vendor_name=vendor.name,
        vendor_address=vendor.address or "",
        vendor_gst=vendor.gst or "",
        items=item_data,
        project_name=project.name or f"Project {project_id}",
        project_ref=f"ACE-{project_id}",
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="PO_{vendor.name}_{project_id}.pdf"',
        },
    )


@router.get("/projects/{project_id}/gantt")
async def generate_project_gantt(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate a Gantt chart SVG from project BOQ items and productivity rates."""
    # Get all BOQ items for this project
    stmt = select(BOQItem).where(
        BOQItem.project_id == project_id,
        BOQItem.is_deleted == False,
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    # Group by trade and compute total quantity per trade
    trade_qty: dict[str, float] = {}
    for item in items:
        trade = item.category or "other"
        trade_qty[trade] = trade_qty.get(trade, 0) + (item.total_qty or item.quantity or 0)

    # Get productivity rates for these trades
    trades = list(trade_qty.keys())
    stmt = select(ProductivityRate).where(
        ProductivityRate.trade.in_(trades),
    )
    result = await db.execute(stmt)
    prod_rates = result.scalars().all()

    prod_map: dict[str, float] = {}
    for pr in prod_rates:
        if pr.trade not in prod_map:
            prod_map[pr.trade] = pr.output_per_day

    # Calculate duration per trade
    tasks = []
    current_day = 0
    for trade in trades:
        qty = trade_qty[trade]
        output_per_day = prod_map.get(trade, 50)  # fallback 50 units/day
        crew_size = 2  # default crew
        duration = math.ceil(qty / (output_per_day * crew_size))
        duration = max(1, duration)

        tasks.append({
            "trade": trade,
            "label": trade.replace("_", " ").title(),
            "duration_days": duration,
            "start_day": current_day,
        })
        current_day += duration  # sequential by default

    svg = generate_gantt_svg(
        tasks=tasks,
        title=f"Project Gantt — {project.name if project else project_id}",
    )

    return Response(
        content=svg,
        media_type="image/svg+xml",
    )
