"""Verify seed data integrity.

Runs after seed data is loaded to ensure critical business constraints are met.
This is a post-seed safety check that fails the migration if data quality gates
are not satisfied.

Revision ID: 0004_verify_seed_data
Revises: 0003_pgvector_embeddings
Create Date: 2026-07-22
"""
import logging
from typing import Optional

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger("alembic.migration")

revision: str = "0004_verify_seed_data"
down_revision: Optional[str] = "0003_pgvector_embeddings"
branch_labels: Optional[str] = None
depends_on: Optional[str] = None


def upgrade() -> None:
    """Verify seed data integrity after seeding.

    Runs queries against materials, vendors, labour_rates, and wastage_rules
    tables. Raises ValueError if any critical constraint is violated.
    """
    conn = op.get_bind()

    # -- 1. Verify no materials have zero or negative rates --
    result = conn.execute(
        sa.text("SELECT COUNT(*) FROM materials WHERE rate <= 0")
    ).scalar()
    if result and int(result) > 0:
        raise ValueError(
            f"❌ Seed verification FAILED: {result} material(s) have zero or negative rate"
        )
    logger.info("✓ All %d materials have positive rates", result or 0)

    # -- 2. Verify every material has a vendor --
    result = conn.execute(
        sa.text("SELECT COUNT(*) FROM materials WHERE vendor_id IS NULL")
    ).scalar()
    if result and int(result) > 0:
        raise ValueError(
            f"❌ Seed verification FAILED: {result} material(s) have no vendor assigned"
        )
    logger.info("✓ All materials have a vendor assigned")

    # -- 3. Verify every vendor has at least one material --
    result = conn.execute(
        sa.text("""
            SELECT COUNT(*) FROM vendors v
            WHERE NOT EXISTS (
                SELECT 1 FROM materials m WHERE m.vendor_id = v.id
            )
        """)
    ).scalar()
    if result and int(result) > 0:
        raise ValueError(
            f"❌ Seed verification FAILED: {result} vendor(s) have no materials"
        )
    logger.info("✓ Every vendor has at least one material")

    # -- 4. Verify labour rates have positive total_rate --
    result = conn.execute(
        sa.text("SELECT COUNT(*) FROM labour_rates WHERE total_rate <= 0")
    ).scalar()
    if result and int(result) > 0:
        raise ValueError(
            f"❌ Seed verification FAILED: {result} labour rate(s) have zero or negative total_rate"
        )
    logger.info("✓ All labour rates have positive total_rate")

    # -- 5. Verify wastage rules have valid percentages --
    result = conn.execute(
        sa.text("""
            SELECT COUNT(*) FROM wastage_rules
            WHERE wastage_pct < 0 OR wastage_pct > 100
        """)
    ).scalar()
    if result and int(result) > 0:
        raise ValueError(
            f"❌ Seed verification FAILED: {result} wastage rule(s) have invalid percentages"
        )
    logger.info("✓ All wastage rules have valid percentages (0-100)")

    # -- 6. Verify productivity rates have positive output --
    result = conn.execute(
        sa.text("SELECT COUNT(*) FROM productivity_rates WHERE output_per_day <= 0")
    ).scalar()
    if result and int(result) > 0:
        raise ValueError(
            f"❌ Seed verification FAILED: {result} productivity rate(s) have zero or negative output_per_day"
        )
    logger.info("✓ All productivity rates have positive output_per_day")

    # -- 7. Verify company standards exist --
    result = conn.execute(
        sa.text("SELECT COUNT(*) FROM company_standards")
    ).scalar()
    if not result or int(result) == 0:
        raise ValueError(
            "❌ Seed verification FAILED: No company standards loaded"
        )
    logger.info("✓ %d company standards loaded", result)

    # -- 8. Check Jasfo Design company info exists --
    result = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM company_standards WHERE category = 'company'"
        )
    ).scalar()
    if not result or int(result) == 0:
        logger.warning("⚠ No company info standards found (category='company')")
    else:
        logger.info("✓ Company info standards present")

    # -- 9. Verify BOQ rules have valid sub_items --
    result = conn.execute(
        sa.text("SELECT COUNT(*) FROM boq_rules WHERE sub_items IS NULL OR sub_items = '[]'::jsonb")
    ).scalar()
    if result and int(result) > 0:
        logger.warning("⚠ %d BOQ rule(s) have empty sub_items", result)
    else:
        logger.info("✓ All BOQ rules have sub_items")

    # -- 10. Summary counts --
    for table, label in [
        ("vendors", "Vendors"),
        ("materials", "Materials"),
        ("labour_rates", "Labour rates"),
        ("wastage_rules", "Wastage rules"),
        ("productivity_rates", "Productivity rates"),
        ("company_standards", "Company standards"),
        ("boq_rules", "BOQ rules"),
    ]:
        count = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        logger.info("  %s: %d", label, count)

    logger.info("✅ Seed data verification passed")


def downgrade() -> None:
    """No structural changes to revert."""
    pass
