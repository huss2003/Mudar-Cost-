#!/usr/bin/env python3
"""Auto Cost Engine — Seed Runner

Loads rule libraries, reference data, and sample materials into the database.

Usage:
    python seed/run_seed.py            # Seed everything
    python seed/run_seed.py --materials-only   # Only materials/vendors
    python seed/run_seed.py --rules-only       # Only rules data
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

# Ensure the backend directory is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.database import engine, async_session, Base
from app.models import (
    BOQRule, WastageRule, ProductivityRate, CompanyStandard,
    DrawingObjectType, Material, Vendor, LabourRate,
    User, Project, Drawing, DetectedObject, BOQItem,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

SEED_DIR = Path(__file__).resolve().parent
RULES_DIR = SEED_DIR / "rules"
REF_DIR = SEED_DIR / "reference"


# =============================================================================
# Rule import functions
# =============================================================================

async def import_boq_rules(session: AsyncSession) -> int:
    """Load BOQ expansion rules from YAML."""
    path = RULES_DIR / "boq_rules.yaml"
    if not path.exists():
        print(f"  ⚠  {path.name} not found — skipping")
        return 0

    with open(path) as f:
        data = yaml.safe_load(f)

    count = 0
    for rule_data in data.get("rules", []):
        sub_items = rule_data.get("sub_items", [])
        rule = BOQRule(
            object_type=rule_data["object_type"],
            name=rule_data["name"],
            description=rule_data.get("description", ""),
            trade=rule_data.get("trade", ""),
            formula=rule_data.get("formula", ""),
            sub_items=sub_items,
            is_active=True,
            version=1,
        )
        session.add(rule)
        count += 1

    await session.commit()
    print(f"  ✓ {count} BOQ rules loaded")
    return count


async def import_wastage_rules(session: AsyncSession) -> int:
    """Load wastage rules from YAML."""
    path = RULES_DIR / "wastage_rules.yaml"
    if not path.exists():
        print(f"  ⚠  {path.name} not found — skipping")
        return 0

    with open(path) as f:
        data = yaml.safe_load(f)

    count = 0
    for rule_data in data.get("rules", []):
        rule = WastageRule(
            material_category=rule_data["material_category"],
            material_subcategory=rule_data.get("material_subcategory"),
            wastage_pct=rule_data["wastage_pct"],
            description=rule_data.get("description", ""),
            applicable_to=rule_data.get("applicable_to", "material"),
            region=rule_data.get("region"),
            is_mandatory=rule_data.get("is_mandatory", False),
        )
        session.add(rule)
        count += 1

    await session.commit()
    print(f"  ✓ {count} wastage rules loaded")
    return count


async def import_productivity_rates(session: AsyncSession) -> int:
    """Load productivity rates from YAML."""
    path = RULES_DIR / "productivity_rates.yaml"
    if not path.exists():
        print(f"  ⚠  {path.name} not found — skipping")
        return 0

    with open(path) as f:
        data = yaml.safe_load(f)

    count = 0
    for rate_data in data.get("rates", []):
        rate = ProductivityRate(
            trade=rate_data["trade"],
            activity=rate_data["activity"],
            unit=rate_data.get("unit", "sqm"),
            output_per_day=rate_data["output_per_day"],
            crew_size=rate_data.get("crew_size", 1),
            crew_composition=rate_data.get("crew_composition", {}),
            equipment_needed=rate_data.get("equipment_needed", []),
            notes=rate_data.get("notes"),
        )
        session.add(rate)
        count += 1

    await session.commit()
    print(f"  ✓ {count} productivity rates loaded")
    return count


async def import_company_standards(session: AsyncSession) -> int:
    """Load company standards from YAML."""
    path = RULES_DIR / "company_standards.yaml"
    if not path.exists():
        print(f"  ⚠  {path.name} not found — skipping")
        return 0

    with open(path) as f:
        data = yaml.safe_load(f)

    count = 0
    for std_data in data.get("standards", []):
        std = CompanyStandard(
            category=std_data["category"],
            name=std_data["name"],
            value=std_data["value"],
            value_float=std_data.get("value_float"),
            unit=std_data.get("unit"),
            description=std_data.get("description", ""),
            is_global=std_data.get("is_global", True),
            region=std_data.get("region"),
        )
        session.add(std)
        count += 1

    await session.commit()
    print(f"  ✓ {count} company standards loaded")
    return count


async def import_labour_rates(session: AsyncSession) -> int:
    """Load labour rates from YAML."""
    path = RULES_DIR / "labour_rules.yaml"
    if not path.exists():
        print(f"  ⚠  {path.name} not found — skipping")
        return 0

    with open(path) as f:
        data = yaml.safe_load(f)

    count = 0
    for rule_data in data.get("rules", []):
        rate = LabourRate(
            trade=rule_data["trade"],
            description=rule_data.get("description"),
            skill_level=rule_data.get("skill_level"),
            unit=rule_data.get("unit", "day"),
            basic_rate=rule_data.get("basic_rate", 0),
            hra=rule_data.get("hra", 0),
            conveyance=rule_data.get("conveyance", 0),
            food_allowance=rule_data.get("food_allowance", 0),
            insurance=rule_data.get("insurance", 0),
            other_allowances=rule_data.get("other_allowances", 0),
            total_rate=rule_data.get("total_rate", 0),
            effective_date=rule_data.get("effective_date"),
            city_category=rule_data.get("city_category"),
            is_union_rate=rule_data.get("is_union_rate", False),
            notes=rule_data.get("notes"),
        )
        session.add(rate)
        count += 1

    await session.commit()
    print(f"  ✓ {count} labour rates loaded")
    return count


async def import_reference_vendors(session: AsyncSession) -> int:
    """Load vendors from reference YAML."""
    path = REF_DIR / "vendors.yaml"
    if not path.exists():
        print(f"  ⚠  {path.name} not found — skipping")
        return 0

    with open(path) as f:
        data = yaml.safe_load(f)

    count = 0
    for v_data in data.get("vendors", []):
        existing = await session.execute(
            select(Vendor).where(Vendor.vendor_code == v_data["vendor_code"])
        )
        if existing.scalar_one_or_none():
            continue
        vendor = Vendor(
            name=v_data["name"],
            vendor_code=v_data.get("vendor_code"),
            contact_person=v_data.get("contact_person"),
            email=v_data.get("email"),
            phone=v_data.get("phone"),
            website=v_data.get("website"),
            city=v_data.get("city"),
            address=v_data.get("address"),
            gst=v_data.get("gst"),
            payment_terms=v_data.get("payment_terms"),
            delivery_time_days=v_data.get("delivery_time_days", 7),
            moq=v_data.get("moq", 1),
            rating=v_data.get("rating", 0),
            categories_served=v_data.get("categories_served", []),
            is_approved=v_data.get("is_approved", False),
            credit_limit=v_data.get("credit_limit", 0),
            notes=v_data.get("notes"),
            bank_details=v_data.get("bank_details"),
        )
        session.add(vendor)
        count += 1

    await session.commit()
    print(f"  ✓ {count} vendors loaded from reference")
    return count


async def import_reference_materials(session: AsyncSession) -> int:
    """Load materials from reference YAML, cross-referencing vendors."""
    path = REF_DIR / "materials.yaml"
    if not path.exists():
        print(f"  ⚠  {path.name} not found — skipping")
        return 0

    with open(path) as f:
        data = yaml.safe_load(f)

    # Build vendor_code -> id map
    vendor_map = {}
    result = await session.execute(select(Vendor))
    for v in result.scalars():
        if v.vendor_code:
            vendor_map[v.vendor_code] = v.id

    count = 0
    for m_data in data.get("materials", []):
        existing = await session.execute(
            select(Material).where(Material.sku == m_data["sku"])
        )
        if existing.scalar_one_or_none():
            continue

        vendor_code = m_data.pop("vendor_id_ref", None)
        vendor_id = vendor_map.get(vendor_code) if vendor_code else None

        material = Material(
            **m_data,
            vendor_id=vendor_id,
        )
        session.add(material)
        count += 1

    await session.commit()
    print(f"  ✓ {count} materials loaded from reference (from {len(data.get('materials', []))} defined)")
    return count


# =============================================================================
# Drawing Object Type seed data
# =============================================================================

DRAWING_OBJECT_TYPES = [
    {
        "name": "gypsum_partition",
        "display_name": "Gypsum Partition",
        "category": "finish",
        "default_unit": "sqm",
        "icon": "wall",
        "description": "Standard gypsum board partition with metal stud frame",
        "attributes_schema": {"length": "float", "height": "float", "area": "float"},
        "detection_prompt": "gypsum board partition wall metal stud framework",
    },
    {
        "name": "false_ceiling",
        "display_name": "False Ceiling",
        "category": "finish",
        "default_unit": "sqm",
        "icon": "ceiling",
        "description": "False ceiling with metal grid and gypsum/POP boards",
        "attributes_schema": {"length": "float", "width": "float", "area": "float"},
        "detection_prompt": "false ceiling dropped ceiling grid ceiling tiles",
    },
    {
        "name": "carpet_flooring",
        "display_name": "Carpet Flooring",
        "category": "finish",
        "default_unit": "sqm",
        "icon": "floor",
        "description": "Carpet flooring (broadloom or tiles)",
        "attributes_schema": {"length": "float", "width": "float", "area": "float"},
        "detection_prompt": "carpet flooring broadloom carpet tiles",
    },
    {
        "name": "vitrified_tiles",
        "display_name": "Vitrified Tiles",
        "category": "finish",
        "default_unit": "sqm",
        "icon": "tile",
        "description": "Vitrified/ceramic tile flooring",
        "attributes_schema": {"length": "float", "width": "float", "area": "float"},
        "detection_prompt": "vitrified tiles ceramic tiles floor tiling",
    },
    {
        "name": "paint_wall",
        "display_name": "Wall Paint",
        "category": "finish",
        "default_unit": "sqm",
        "icon": "paint",
        "description": "Interior wall painting",
        "attributes_schema": {"length": "float", "width": "float", "height": "float", "area": "float"},
        "detection_prompt": "painted wall emulsion paint wall colour",
    },
    {
        "name": "glass_partition",
        "display_name": "Glass Partition",
        "category": "finish",
        "default_unit": "sqm",
        "icon": "glass",
        "description": "Toughened glass partition",
        "attributes_schema": {"length": "float", "height": "float", "area": "float"},
        "detection_prompt": "glass partition toughened glass frameless glass",
    },
    {
        "name": "wood_door",
        "display_name": "Wooden Door",
        "category": "structure",
        "default_unit": "nos",
        "icon": "door",
        "description": "Flush wooden door with frame",
        "attributes_schema": {"width": "float", "height": "float", "count": "integer"},
        "detection_prompt": "wooden door flush door door frame",
    },
    {
        "name": "electrical_point",
        "display_name": "Electrical Point",
        "category": "mep",
        "default_unit": "point",
        "icon": "electrical",
        "description": "Electrical switch/socket point",
        "attributes_schema": {"count": "integer"},
        "detection_prompt": "electrical point switch socket power outlet",
    },
    {
        "name": "data_point",
        "display_name": "Data Point",
        "category": "mep",
        "default_unit": "point",
        "icon": "data",
        "description": "Network/data outlet point",
        "attributes_schema": {"count": "integer"},
        "detection_prompt": "data point network outlet RJ45 cat6",
    },
]


# =============================================================================
# Master function
# =============================================================================

async def seed_all(args):
    """Run the full seed process."""
    print(f"🔵 Auto Cost Engine — Seed Runner")
    print(f"   Database: {settings.DATABASE_URL}")
    print()

    async with async_session() as session:
        # 1. Drawing Object Types
        if not args.materials_only:
            print("📦 Drawing Object Types...")
            count = 0
            for dot_data in DRAWING_OBJECT_TYPES:
                dot = DrawingObjectType(**dot_data)
                session.add(dot)
                count += 1
            await session.commit()
            print(f"  ✓ {count} drawing object types loaded")
            print()

        # 2. Rule libraries
        if not args.materials_only:
            print("📋 Rule Libraries...")
            await import_boq_rules(session)
            await import_wastage_rules(session)
            await import_productivity_rates(session)
            await import_company_standards(session)
            await import_labour_rates(session)
            print()

        # 3. Materials and vendors
        if not args.rules_only:
            print("🏭 Reference Data...")
            # Import vendors from seed_materials.py (existing)
            from seed.seed_materials import seed_materials_and_vendors
            await seed_materials_and_vendors(session)
            # Also load from reference YAMLs (new, idempotent via SKU/vendor_code)
            await import_reference_vendors(session)
            await import_reference_materials(session)
            print()

    print("✅ Seed complete!")


async def init_db():
    """Create all tables if they don't exist (for non-migration setups)."""
    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    print("  ✓ Tables created / verified")


async def main():
    parser = argparse.ArgumentParser(description="Auto Cost Engine — Seed Runner")
    parser.add_argument("--materials-only", action="store_true", help="Only seed materials/vendors")
    parser.add_argument("--rules-only", action="store_true", help="Only seed rules data")
    parser.add_argument("--init-db", action="store_true", help="Create tables first (bypass Alembic)")
    args = parser.parse_args()

    if args.init_db:
        print("🔄 Initializing database schema...")
        await init_db()
        print()

    await seed_all(args)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
