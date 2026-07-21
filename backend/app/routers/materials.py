"""Material selection & catalogue API endpoints.

Endpoints (all mounted under ``/api/v1`` via ``main.py``):
- GET  /materials                         — list / filter active materials
- GET  /materials/{id}/alternatives       — alternative materials
- GET  /boq-items/{id}/materials          — material options for a BOQ item
- POST /boq-items/{id}/select-material    — assign a material to a BOQ item
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.detection import BOQItem
from app.models.reference import Material
from app.schemas.boq import BOQLineItemResponse
from app.services.live_update import notify_material_change
from app.services.material_selector import (
    find_alternatives,
    get_material_options,
    get_preferred_brands,
    select_material as svc_select_material,
)

# NOTE: prefix is intentionally omitted so that the routes defined here
# match cleanly against the /api/v1 prefix applied in main.py.
# E.g. GET /materials → /api/v1/materials.
router = APIRouter(tags=["materials"])

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class SelectMaterialRequest(BaseModel):
    """Body for POST /boq-items/{id}/select-material."""

    material_id: int


# ---------------------------------------------------------------------------
# BOQ-item material selection
# ---------------------------------------------------------------------------


@router.get("/boq-items/{boq_item_id}/materials")
async def list_material_alternatives(
    boq_item_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all viable material alternatives for a BOQ item.

    Results show preferred brands first. Falls back to a keyword search
    on the item's description when the category has no materials.
    """
    # Validate BOQ item exists
    stmt = select(BOQItem).where(BOQItem.id == boq_item_id)
    result = await db.execute(stmt)
    boq_item = result.scalar_one_or_none()
    if boq_item is None:
        raise HTTPException(
            status_code=404, detail=f"BOQ item {boq_item_id} not found"
        )

    # Fetch preferred brands for the item's category
    preferred_brands: list[str] = []
    if boq_item.category:
        preferred_brands = await get_preferred_brands(db, boq_item.category)

    try:
        return await get_material_options(db, boq_item_id, preferred_brands)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/boq-items/{boq_item_id}/select-material")
async def select_material_for_boq_item(
    boq_item_id: int,
    body: SelectMaterialRequest,
    db: AsyncSession = Depends(get_db),
) -> BOQLineItemResponse:
    """Assign a material to a BOQ line item and update derived fields.

    On success the response is the updated ``BOQLineItemResponse``.
    """
    try:
        boq_item = await svc_select_material(db, boq_item_id, body.material_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Fire background cost-recalculation that pushes SSE updates
    if boq_item.project_id is not None:
        asyncio.create_task(
            notify_material_change(boq_item.project_id, boq_item.id)
        )

    return BOQLineItemResponse(
        id=boq_item.id,
        description=boq_item.description,
        material_code=boq_item.material_name,
        quantity=boq_item.quantity,
        unit=boq_item.unit,
        wastage_pct=boq_item.wastage_pct,
        total_qty=boq_item.quantity,
        rate=boq_item.rate,
        total=boq_item.total,
        source_object_type=None,
        source_object_id=boq_item.object_id,
        hierarchy_level=boq_item.hierarchy_level,
    )


# ---------------------------------------------------------------------------
# Material catalogue
# ---------------------------------------------------------------------------


@router.get("/materials")
async def list_materials(
    category: str = Query(None, description="Filter by material category"),
    brand: str = Query(None, description="Filter by brand name"),
    search: str = Query(None, description="Substring match on material name"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Result offset"),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List active materials, optionally filtered by category / brand / search.

    Results include the vendor name via a joined load.
    """
    filters = [Material.is_active == True]

    if category:
        filters.append(Material.category.ilike(category))
    if brand:
        filters.append(Material.brand.ilike(brand))
    if search:
        filters.append(Material.name.ilike(f"%{search}%"))

    stmt = (
        select(Material)
        .options(joinedload(Material.vendor))
        .where(*filters)
        .order_by(Material.name)
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    materials = result.unique().scalars().all()

    return [
        {
            "material_id": m.id,
            "name": m.name,
            "brand": m.brand,
            "category": m.category,
            "subcategory": m.subcategory,
            "sku": m.sku,
            "rate": m.rate,
            "unit": m.unit,
            "gst_rate": m.gst_rate,
            "vendor_id": m.vendor_id,
            "vendor_name": m.vendor.name if m.vendor else None,
            "lead_time_days": m.lead_time_days,
            "warranty": m.warranty,
            "fire_rating": m.fire_rating,
            "image_url": m.image_url,
            "is_active": m.is_active,
            "moq": m.min_order_qty,
        }
        for m in materials
    ]


@router.get("/materials/{material_id}/alternatives")
async def get_material_alternatives(
    material_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return materials in the same category with similar rates (±30 %).

    Excludes the source material itself.
    """
    # Quick existence check
    stmt = select(Material).where(Material.id == material_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404, detail=f"Material {material_id} not found"
        )

    return await find_alternatives(db, material_id)
