"""Add sha256_hash column to drawings table for SHA-256 dedup.

Revision ID: 0005_add_drawing_sha256
Revises: 0004_add_missing_indexes
Create Date: 2026-07-22
"""
from typing import Optional

import sqlalchemy as sa
from alembic import op

revision: str = "0005_add_drawing_sha256"
down_revision: Optional[str] = "0004_add_missing_indexes"
branch_labels: Optional[str] = None
depends_on: Optional[str] = None


def upgrade() -> None:
    """Add sha256_hash column and a unique index for fast dedup lookups."""
    op.add_column(
        "drawings",
        sa.Column(
            "sha256_hash",
            sa.String(64),
            nullable=True,
            comment="SHA-256 hex digest for dedup",
        ),
    )
    op.create_index(
        "ix_drawings_sha256_hash",
        "drawings",
        ["sha256_hash"],
        postgresql_where=sa.text("sha256_hash IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove the sha256_hash column and its index."""
    op.drop_index("ix_drawings_sha256_hash", table_name="drawings")
    op.drop_column("drawings", "sha256_hash")
