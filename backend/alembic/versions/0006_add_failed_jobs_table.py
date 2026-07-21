"""Add failed_jobs table for Celery dead-letter capture.

Revision ID: 0006_add_failed_jobs_table
Revises: 0005_add_drawing_sha256
Create Date: 2026-07-22
"""
from typing import Optional

import sqlalchemy as sa
from alembic import op

revision: str = "0006_add_failed_jobs_table"
down_revision: Optional[str] = "0005_add_drawing_sha256"
branch_labels: Optional[str] = None
depends_on: Optional[str] = None


def upgrade() -> None:
    """Create the failed_jobs table."""
    op.create_table(
        "failed_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_name", sa.String(255), nullable=False, index=True),
        sa.Column("task_id", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("args", sa.JSON(), nullable=True),
        sa.Column("kwargs", sa.JSON(), nullable=True),
        sa.Column("exc_type", sa.String(255), nullable=True),
        sa.Column("exc_message", sa.Text(), nullable=True),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(36), nullable=True),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop the failed_jobs table."""
    op.drop_table("failed_jobs")
