"""Add missing performance indexes for hot query paths.

Hot paths identified from API query patterns:
- drawings by project_id             [already in 0002: ix_drawings_project_id]
- detected_objects by drawing_id      [MISSING — FK lookup from drawing→objects]
- boq_items by project_id + category  [MISSING — composite for project+trade filtering]
- cost_versions by project_id + created_at DESC  [MISSING — composite for version listing]
- vendors by city                     [MISSING — city-based vendor filtering]

NOTE: The following indexes already exist from earlier migrations and are NOT
re-created here:
  - ix_detected_objects_object_type  (0001_initial_schema)
  - ix_boq_items_category             (0001_initial_schema)
  - materials.sku unique constraint   (0001_initial_schema — auto-creates B-tree index)

Revision ID: 0004_add_missing_indexes
Revises: 0003_pgvector_embeddings
Create Date: 2026-07-22
"""
from typing import Optional

import sqlalchemy as sa
from alembic import op

revision: str = "0004_add_missing_indexes"
down_revision: Optional[str] = "0003_pgvector_embeddings"
branch_labels: Optional[str] = None
depends_on: Optional[str] = None


def upgrade() -> None:
    """Create indexes on hot query paths that are not yet covered."""

    # -- detected_objects.drawing_id (FK lookup: drawing → detected objects) --
    op.create_index(
        "ix_detected_objects_drawing",
        "detected_objects",
        ["drawing_id"],
    )

    # -- boq_items(project_id, category) — composite for project+trade filtering --
    op.create_index(
        "ix_boq_items_project_trade",
        "boq_items",
        ["project_id", sa.text("category")],
    )

    # -- cost_versions(project_id, created_at DESC) — version listing sorted by recency --
    op.create_index(
        "ix_cost_versions_project_created",
        "cost_versions",
        ["project_id", sa.text("created_at DESC")],
    )

    # -- vendors.city — city-based vendor lookups --
    op.create_index(
        "ix_vendors_city",
        "vendors",
        ["city"],
    )


def downgrade() -> None:
    """Remove the indexes added in this migration."""
    op.drop_index("ix_detected_objects_drawing", table_name="detected_objects")
    op.drop_index("ix_boq_items_project_trade", table_name="boq_items")
    op.drop_index("ix_cost_versions_project_created", table_name="cost_versions")
    op.drop_index("ix_vendors_city", table_name="vendors")
