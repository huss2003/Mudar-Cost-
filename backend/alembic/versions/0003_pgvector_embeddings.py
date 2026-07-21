"""Add pgvector embedding columns to projects and boq_items.

Revision ID: 0003_pgvector_embeddings
Revises: 0002_full_schema
Create Date: 2026-07-21
"""
from typing import Optional

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0003_pgvector_embeddings"
down_revision: Optional[str] = "0002_full_schema"
branch_labels: Optional[str] = None
depends_on: Optional[str] = None


def upgrade() -> None:
    """Add embedding (Vector(384)) columns to projects and boq_items."""

    # Ensure pgvector extension is enabled (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # -- projects.embedding --
    op.add_column(
        "projects",
        sa.Column("embedding", Vector(384), nullable=True),
    )
    op.create_index(
        "ix_projects_embedding",
        "projects",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
    )

    # -- boq_items.embedding --
    op.add_column(
        "boq_items",
        sa.Column("embedding", Vector(384), nullable=True),
    )
    op.create_index(
        "ix_boq_items_embedding",
        "boq_items",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
    )


def downgrade() -> None:
    """Remove embedding columns and their indexes."""
    op.drop_index("ix_boq_items_embedding", table_name="boq_items")
    op.drop_column("boq_items", "embedding")
    op.drop_index("ix_projects_embedding", table_name="projects")
    op.drop_column("projects", "embedding")
