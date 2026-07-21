"""Service layer for material selection and alternative discovery.

Provides:
- get_material_options: list candidate materials for a BOQ item
- select_material: assign a material to a BOQ item and update derived fields
- find_alternatives: discover alternatives for a given material
- get_preferred_brands: read brand preferences from company standards
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.detection import BOQItem, CostVersion
from app.models.history import RateHistory
from app.models.reference import Material, Vendor
from app.models.rules import CompanyStandard


async def get_preferred_brands(
    db: AsyncSession, category: str
) -> list[str]:
    """Return brand names marked as preferred for *category*.

    Looks up ``CompanyStandard`` rows whose category is ``"brand_preference"``
    and name equals the material *category*.
    """
    stmt = select(CompanyStandard).where(
        CompanyStandard.category == "brand_preference",
        CompanyStandard.name == category,
    )
    result = await db.execute(stmt)
    return [s.value for s in result.scalars().all() if s.value]


async def get_material_options(
    db: AsyncSession,
    boq_item_id: int,
    preferred_brands: Optional[list[str]] = None,
) -> list[dict]:
    """Return material alternatives for *boq_item_id*.

    1. Look up the BOQ item (raises ``ValueError`` if missing).
    2. Query active materials whose category matches the BOQ item's category.
    3. If no category match is found, fall back to a keyword-based search
       using the BOQ item description.
    4. Join vendor information.
    5. Tag preferred brands (``is_preferred: true``) and sort them first.
    """
    stmt = select(BOQItem).where(BOQItem.id == boq_item_id)
    result = await db.execute(stmt)
    boq_item = result.scalar_one_or_none()
    if boq_item is None:
        raise ValueError(f"BOQItem {boq_item_id} not found")

    preferred_set = set(preferred_brands or [])
    category = boq_item.category
    materials: list[Material] = []

    # --- Primary: category match -------------------------------------------
    if category:
        stmt = (
            select(Material)
            .options(joinedload(Material.vendor))
            .where(Material.category == category, Material.is_active == True)
            .order_by(Material.name)
        )
        result = await db.execute(stmt)
        materials = list(result.unique().scalars().all())

    # --- Fallback: name / description keyword search -----------------------
    if not materials:
        keywords = [
            w.strip().lower()
            for w in (boq_item.description or "").split()
            if len(w.strip()) > 2
        ][:5]
        if keywords:
            name_filters = [Material.name.ilike(f"%{kw}%") for kw in keywords]
            stmt = (
                select(Material)
                .options(joinedload(Material.vendor))
                .where(Material.is_active == True, or_(*name_filters))
                .order_by(Material.name)
                .limit(20)
            )
            result = await db.execute(stmt)
            materials = list(result.unique().scalars().all())

    # --- Build response list -----------------------------------------------
    out: list[dict] = []
    for m in materials:
        is_preferred = bool(m.brand and m.brand in preferred_set)
        out.append(
            {
                "material_id": m.id,
                "name": m.name,
                "brand": m.brand,
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
                "is_preferred": is_preferred,
                "moq": m.min_order_qty,
            }
        )

    # Preferred brands first, then alphabetical by name
    out.sort(key=lambda x: (not x["is_preferred"], x["name"] or ""))
    return out


async def select_material(
    db: AsyncSession,
    boq_item_id: int,
    material_id: int,
) -> BOQItem:
    """Assign *material_id* to *boq_item_id* and update derived fields.

    Side-effects:
    - Sets ``BOQItem.rate`` = material.rate
    - Sets ``BOQItem.total`` = quantity × rate
    - Sets ``BOQItem.vendor_id`` = material.vendor_id
    - Downgrades any ``approved`` cost versions for the same project to
      ``draft``.
    - Logs a ``RateHistory`` row.

    Raises ``ValueError`` if either the BOQ item or material is missing.
    """
    # --- Fetch BOQ item ----------------------------------------------------
    stmt = select(BOQItem).where(BOQItem.id == boq_item_id)
    result = await db.execute(stmt)
    boq_item = result.scalar_one_or_none()
    if boq_item is None:
        raise ValueError(f"BOQItem {boq_item_id} not found")

    # --- Fetch material ----------------------------------------------------
    stmt = select(Material).where(Material.id == material_id)
    result = await db.execute(stmt)
    material = result.scalar_one_or_none()
    if material is None:
        raise ValueError(f"Material {material_id} not found")

    old_rate = boq_item.rate

    # --- Update fields -----------------------------------------------------
    boq_item.material_id = material.id
    boq_item.material_name = material.name
    boq_item.rate = material.rate
    boq_item.vendor_id = material.vendor_id
    boq_item.total = boq_item.quantity * material.rate

    # --- Invalidate approved cost versions ---------------------------------
    if boq_item.project_id is not None:
        cv_stmt = select(CostVersion).where(
            CostVersion.project_id == boq_item.project_id,
            CostVersion.status == "approved",
        )
        cv_result = await db.execute(cv_stmt)
        for cv in cv_result.scalars().all():
            cv.status = "draft"

    # --- Log rate change ---------------------------------------------------
    rate_history = RateHistory(
        reference_type="material",
        reference_id=material.id,
        old_rate=old_rate,
        new_rate=material.rate,
        change_reason=f"Material selected for BOQ item {boq_item_id}",
    )
    db.add(rate_history)

    await db.flush()
    return boq_item


async def find_alternatives(
    db: AsyncSession,
    material_id: int,
) -> list[dict]:
    """Return alternative materials for *material_id*.

    Alternatives are active materials in the same category with a rate within
    ±30 % of the source material's rate, excluding the source itself.
    Results are ordered by rate (lowest first).
    Returns an empty list if the source material does not exist.
    """
    stmt = select(Material).where(Material.id == material_id)
    result = await db.execute(stmt)
    material = result.scalar_one_or_none()
    if material is None:
        return []

    rate_min = material.rate * 0.70
    rate_max = material.rate * 1.30

    stmt = (
        select(Material)
        .options(joinedload(Material.vendor))
        .where(
            Material.category == material.category,
            Material.is_active == True,
            Material.id != material_id,
            Material.rate >= rate_min,
            Material.rate <= rate_max,
        )
        .order_by(Material.rate)
    )
    result = await db.execute(stmt)
    alternatives = list(result.unique().scalars().all())

    return [
        {
            "material_id": m.id,
            "name": m.name,
            "brand": m.brand,
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
            "moq": m.min_order_qty,
        }
        for m in alternatives
    ]
