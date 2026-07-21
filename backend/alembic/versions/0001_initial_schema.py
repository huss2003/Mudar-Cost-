"""Initial database schema.

Create all core tables for the Cost Estimation Engine.
"""

from typing import Optional

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: Optional[str] = None
branch_labels: Optional[str] = None
depends_on: Optional[str] = None


def upgrade() -> None:
    # ── Projects ────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("client", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("total_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_labour", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_materials", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_transport", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_overhead", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_margin", sa.Float(), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_status"), "projects", ["status"])

    # ── Drawings ────────────────────────────────────────────────────
    op.create_table(
        "drawings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "upload_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("status", sa.String(50), nullable=False, server_default="uploaded"),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("thumbnail_path", sa.String(512), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Materials ───────────────────────────────────────────────────
    op.create_table(
        "materials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("brand", sa.String(255), nullable=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(50), nullable=False, server_default="nos"),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("warranty", sa.String(255), nullable=True),
        sa.Column("fire_rating", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("min_order_qty", sa.Float(), nullable=True, server_default="1"),
        sa.Column("lead_time_days", sa.Integer(), nullable=True, server_default="7"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku"),
    )
    op.create_index(op.f("ix_materials_category"), "materials", ["category"])
    op.create_index(op.f("ix_materials_name"), "materials", ["name"])

    # ── Vendors ─────────────────────────────────────────────────────
    op.create_table(
        "vendors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_person", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("gst", sa.String(50), nullable=True),
        sa.Column("delivery_time_days", sa.Integer(), nullable=True, server_default="7"),
        sa.Column("moq", sa.Float(), nullable=True, server_default="1"),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Rules ───────────────────────────────────────────────────────
    op.create_table(
        "rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("object_type", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sub_items_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_type"),
    )
    op.create_index(op.f("ix_rules_object_type"), "rules", ["object_type"])

    # ── Detected Objects ────────────────────────────────────────────
    op.create_table(
        "detected_objects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("object_type", sa.String(100), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("length", sa.Float(), nullable=True),
        sa.Column("width", sa.Float(), nullable=True),
        sa.Column("area", sa.Float(), nullable=True),
        sa.Column("height", sa.Float(), nullable=True),
        sa.Column("thickness", sa.Float(), nullable=True),
        sa.Column("layer", sa.String(100), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("bbox_coords", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_detected_objects_object_type"),
        "detected_objects",
        ["object_type"],
    )

    # ── BOQ Items ───────────────────────────────────────────────────
    op.create_table(
        "boq_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "object_id",
            sa.Integer(),
            sa.ForeignKey("detected_objects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(50), nullable=False, server_default="nos"),
        sa.Column("rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("labour_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("transport_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("overhead_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("margin_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "material_id",
            sa.Integer(),
            sa.ForeignKey("materials.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("material_name", sa.String(255), nullable=True),
        sa.Column(
            "vendor_id",
            sa.Integer(),
            sa.ForeignKey("vendors.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_boq_items_category"), "boq_items", ["category"])


def downgrade() -> None:
    op.drop_table("boq_items")
    op.drop_table("detected_objects")
    op.drop_table("rules")
    op.drop_table("vendors")
    op.drop_table("materials")
    op.drop_table("drawings")
    op.drop_table("projects")
