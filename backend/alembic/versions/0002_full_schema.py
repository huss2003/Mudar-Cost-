"""Full database schema — all 15 datasets + core tables.

Adds columns to existing 0001 tables and creates all missing tables
for the complete Cost Estimation Engine data foundation.

Revision ID: 0002_full_schema
Revises: 0001_initial_schema
Create Date: 2026-07-21
"""
from typing import Optional

import sqlalchemy as sa
from alembic import op

revision: str = "0002_full_schema"
down_revision: Optional[str] = "0001_initial_schema"
branch_labels: Optional[str] = None
depends_on: Optional[str] = None


def upgrade() -> None:
    """Apply the full schema upgrade."""

    # ═══════════════════════════════════════════════════════════════════
    # Enable pgvector extension
    # ═══════════════════════════════════════════════════════════════════
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ═══════════════════════════════════════════════════════════════════
    # ENHANCE EXISTING TABLES (from 0001_initial_schema)
    # ═══════════════════════════════════════════════════════════════════

    # -- Projects: add new columns --
    op.add_column("projects", sa.Column("project_code", sa.String(50), nullable=True))
    op.add_column("projects", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("projects", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column("projects", sa.Column("client_ref", sa.String(255), nullable=True))
    op.add_column("projects", sa.Column("site_address", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("gst_hst", sa.String(50), nullable=True))
    op.add_column("projects", sa.Column("po_number", sa.String(100), nullable=True))
    op.add_column("projects", sa.Column("currency", sa.String(3), server_default="INR", nullable=False))
    op.add_column("projects", sa.Column("created_by", sa.Integer(), nullable=True))
    op.add_column("projects", sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("projects", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_projects_project_code", "projects", ["project_code"])
    op.create_foreign_key("fk_projects_created_by", "projects", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_projects_project_code", "projects", ["project_code"])

    # -- Drawings: add new columns --
    op.add_column("drawings", sa.Column("project_id", sa.Integer(), nullable=False))
    op.add_column("drawings", sa.Column("minio_object_key", sa.String(512), nullable=True))
    op.add_column("drawings", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("drawings", sa.Column("scale", sa.String(50), nullable=True))
    op.add_column("drawings", sa.Column("page_count", sa.Integer(), server_default="1", nullable=True))
    op.add_column("drawings", sa.Column("revision", sa.Integer(), server_default="1", nullable=True))
    op.add_column("drawings", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("drawings", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("drawings", sa.Column("uploaded_by", sa.Integer(), nullable=True))
    op.add_column("drawings", sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("drawings", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("drawings", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.add_column("drawings", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_foreign_key("fk_drawings_project", "drawings", "projects", ["project_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_drawings_uploaded_by", "drawings", "users", ["uploaded_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_drawings_project_id", "drawings", ["project_id"])

    # -- Materials: add new columns --
    op.add_column("materials", sa.Column("subcategory", sa.String(100), nullable=True))
    op.add_column("materials", sa.Column("hsn_code", sa.String(20), nullable=True))
    op.add_column("materials", sa.Column("gst_rate", sa.Float(), server_default="18", nullable=True))
    op.add_column("materials", sa.Column("cess", sa.Float(), server_default="0", nullable=True))
    op.add_column("materials", sa.Column("moq_description", sa.String(255), nullable=True))
    op.add_column("materials", sa.Column("vendor_id", sa.Integer(), nullable=True))
    op.add_column("materials", sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("materials", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column("materials", sa.Column("alternative_material_ids", sa.JSON(), nullable=True))
    op.add_column("materials", sa.Column("has_variants", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("materials", sa.Column("parent_material_id", sa.Integer(), nullable=True))
    op.add_column("materials", sa.Column("embedding", sa.Float(precision=53), nullable=True))
    op.add_column("materials", sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("materials", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("materials", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.add_column("materials", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_foreign_key("fk_materials_vendor", "materials", "vendors", ["vendor_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_materials_parent", "materials", "materials", ["parent_material_id"], ["id"], ondelete="SET NULL")

    # -- Vendors: add new columns --
    op.add_column("vendors", sa.Column("vendor_code", sa.String(50), nullable=True))
    op.add_column("vendors", sa.Column("website", sa.String(255), nullable=True))
    op.add_column("vendors", sa.Column("payment_terms", sa.String(255), nullable=True))
    op.add_column("vendors", sa.Column("bank_details", sa.Text(), nullable=True))
    op.add_column("vendors", sa.Column("categories_served", sa.JSON(), nullable=True))
    op.add_column("vendors", sa.Column("is_approved", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("vendors", sa.Column("approval_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("vendors", sa.Column("credit_limit", sa.Float(), server_default="0", nullable=True))
    op.add_column("vendors", sa.Column("embedding", sa.Float(precision=53), nullable=True))
    op.add_column("vendors", sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("vendors", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("vendors", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.add_column("vendors", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_unique_constraint("uq_vendors_vendor_code", "vendors", ["vendor_code"])

    # -- Detected Objects: add new columns --
    op.add_column("detected_objects", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.add_column("detected_objects", sa.Column("polyline_json", sa.Text(), nullable=True))
    op.add_column("detected_objects", sa.Column("embedding", sa.Float(precision=53), nullable=True))
    op.add_column("detected_objects", sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("detected_objects", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("detected_objects", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_foreign_key("fk_detected_objects_parent", "detected_objects", "detected_objects", ["parent_id"], ["id"], ondelete="SET NULL")

    # -- BOQ Items: add new columns --
    op.add_column("boq_items", sa.Column("code", sa.String(50), nullable=True))
    op.add_column("boq_items", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.add_column("boq_items", sa.Column("hierarchy_level", sa.Integer(), server_default="0", nullable=False))
    op.add_column("boq_items", sa.Column("is_expanded", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("boq_items", sa.Column("rule_id", sa.Integer(), nullable=True))
    op.add_column("boq_items", sa.Column("wastage_pct", sa.Float(), server_default="0", nullable=False))
    op.add_column("boq_items", sa.Column("wastage_cost", sa.Float(), server_default="0", nullable=False))
    op.add_column("boq_items", sa.Column("transport_cost", sa.Float(), server_default="0", nullable=False))
    op.add_column("boq_items", sa.Column("overhead_cost", sa.Float(), server_default="0", nullable=False))
    op.add_column("boq_items", sa.Column("margin_cost", sa.Float(), server_default="0", nullable=False))
    op.add_column("boq_items", sa.Column("base_cost", sa.Float(), server_default="0", nullable=False))
    op.add_column("boq_items", sa.Column("total_cost", sa.Float(), server_default="0", nullable=False))
    op.add_column("boq_items", sa.Column("approval_status", sa.String(20), server_default="pending", nullable=False))
    op.add_column("boq_items", sa.Column("approved_by", sa.Integer(), nullable=True))
    op.add_column("boq_items", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("boq_items", sa.Column("revision", sa.Integer(), server_default="1", nullable=False))
    op.add_column("boq_items", sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False))
    op.add_column("boq_items", sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("boq_items", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("boq_items", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_foreign_key("fk_boq_items_parent", "boq_items", "boq_items", ["parent_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_boq_items_rule", "boq_items", "boq_rules", ["rule_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_boq_items_approved_by", "boq_items", "users", ["approved_by"], ["id"], ondelete="SET NULL")

    # ═══════════════════════════════════════════════════════════════════
    # NEW TABLES
    # ═══════════════════════════════════════════════════════════════════

    # -- Users (core auth) --
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sub", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(50), server_default="estimator", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sub"),
    )
    op.create_index("ix_users_sub", "users", ["sub"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_role", "users", ["role"])

    # -- Drawing Object Type Library --
    op.create_table(
        "drawing_object_types",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("default_unit", sa.String(20), server_default="sqm"),
        sa.Column("icon", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("attributes_schema", sa.JSON(), nullable=True),
        sa.Column("detection_prompt", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_drawing_object_types_name", "drawing_object_types", ["name"])
    op.create_index("ix_drawing_object_types_category", "drawing_object_types", ["category"])

    # -- BOQ Rule Library (replaces old rules table) --
    op.create_table(
        "boq_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("object_type", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trade", sa.String(50), nullable=True),
        sa.Column("formula", sa.Text(), nullable=True),
        sa.Column("sub_items", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_type", "version", name="uq_boq_rules_object_type_version"),
    )
    op.create_index("ix_boq_rules_object_type", "boq_rules", ["object_type"])

    # -- Labour Rate --
    op.create_table(
        "labour_rates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trade", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("skill_level", sa.String(50), nullable=True),
        sa.Column("unit", sa.String(20), server_default="day"),
        sa.Column("basic_rate", sa.Float(), server_default="0"),
        sa.Column("hra", sa.Float(), server_default="0"),
        sa.Column("conveyance", sa.Float(), server_default="0"),
        sa.Column("food_allowance", sa.Float(), server_default="0"),
        sa.Column("insurance", sa.Float(), server_default="0"),
        sa.Column("other_allowances", sa.Float(), server_default="0"),
        sa.Column("total_rate", sa.Float(), server_default="0"),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("city_category", sa.String(20), nullable=True),
        sa.Column("is_union_rate", sa.Boolean(), server_default="false"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_labour_rates_trade", "labour_rates", ["trade"])

    # -- Wastage Rules --
    op.create_table(
        "wastage_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("material_category", sa.String(100), nullable=False),
        sa.Column("material_subcategory", sa.String(100), nullable=True),
        sa.Column("wastage_pct", sa.Float(), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("applicable_to", sa.String(50), server_default="material"),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("is_mandatory", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wastage_rules_category", "wastage_rules", ["material_category"])

    # -- Productivity Rates --
    op.create_table(
        "productivity_rates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trade", sa.String(50), nullable=False),
        sa.Column("activity", sa.String(255), nullable=False),
        sa.Column("unit", sa.String(20), server_default="sqm"),
        sa.Column("output_per_day", sa.Float(), nullable=False),
        sa.Column("crew_size", sa.Integer(), server_default="1"),
        sa.Column("crew_composition", sa.JSON(), nullable=True),
        sa.Column("equipment_needed", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_productivity_rates_trade", "productivity_rates", ["trade"])

    # -- Company Standards --
    op.create_table(
        "company_standards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("value", sa.String(255), nullable=True),
        sa.Column("value_float", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_global", sa.Boolean(), server_default="true"),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category", "name", "region", name="uq_company_standards"),
    )

    # -- Design & 3D Asset Library --
    op.create_table(
        "design_assets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("asset_type", sa.String(50), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("minio_object_key", sa.String(512), nullable=False),
        sa.Column("thumbnail_key", sa.String(512), nullable=True),
        sa.Column("file_format", sa.String(20), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("license", sa.String(100), nullable=True),
        sa.Column("is_public", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_design_assets_type", "design_assets", ["asset_type"])

    # -- Client Templates --
    op.create_table(
        "client_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("client_type", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("template_json", sa.JSON(), nullable=True),
        sa.Column("default_markup_pct", sa.Float(), server_default="15"),
        sa.Column("default_margin_pct", sa.Float(), server_default="10"),
        sa.Column("sections", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- Cost Versions --
    op.create_table(
        "cost_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("total_cost", sa.Float(), server_default="0"),
        sa.Column("total_materials", sa.Float(), server_default="0"),
        sa.Column("total_labour", sa.Float(), server_default="0"),
        sa.Column("total_wastage", sa.Float(), server_default="0"),
        sa.Column("total_transport", sa.Float(), server_default="0"),
        sa.Column("total_overhead", sa.Float(), server_default="0"),
        sa.Column("total_margin", sa.Float(), server_default="0"),
        sa.Column("grand_total", sa.Float(), server_default="0"),
        sa.Column("currency", sa.String(3), server_default="INR"),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "version_number", name="uq_cost_versions_project_version"),
    )
    op.create_foreign_key("fk_cost_versions_project", "cost_versions", "projects", ["project_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_cost_versions_created_by", "cost_versions", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_cost_versions_approved_by", "cost_versions", "users", ["approved_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_cost_versions_project", "cost_versions", ["project_id"])

    # -- Rate History --
    op.create_table(
        "rate_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reference_type", sa.String(50), nullable=False),
        sa.Column("reference_id", sa.Integer(), nullable=False),
        sa.Column("old_rate", sa.Float(), nullable=True),
        sa.Column("new_rate", sa.Float(), nullable=True),
        sa.Column("old_gst", sa.Float(), nullable=True),
        sa.Column("new_gst", sa.Float(), nullable=True),
        sa.Column("change_reason", sa.String(255), nullable=True),
        sa.Column("changed_by", sa.Integer(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key("fk_rate_history_changed_by", "rate_history", "users", ["changed_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_rate_history_reference", "rate_history", ["reference_type", "reference_id"])

    # -- Project History --
    op.create_table(
        "project_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("field_changed", sa.String(100), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("change_type", sa.String(50), nullable=True),
        sa.Column("changed_by", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key("fk_project_history_project", "project_history", "projects", ["project_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_project_history_changed_by", "project_history", "users", ["changed_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_project_history_project", "project_history", ["project_id"])

    # -- Revision History --
    op.create_table(
        "revision_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=True),
        sa.Column("revision_type", sa.String(50), nullable=True),
        sa.Column("reference_type", sa.String(50), nullable=True),
        sa.Column("reference_id", sa.Integer(), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key("fk_revision_history_project", "revision_history", "projects", ["project_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_revision_history_approved_by", "revision_history", "users", ["approved_by"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_revision_history_created_by", "revision_history", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_revision_history_project", "revision_history", ["project_id"])

    # -- Procurement History --
    op.create_table(
        "procurement_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("po_number", sa.String(100), nullable=True),
        sa.Column("vendor_id", sa.Integer(), nullable=True),
        sa.Column("material_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Float(), server_default="0"),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("unit_rate", sa.Float(), server_default="0"),
        sa.Column("total_amount", sa.Float(), server_default="0"),
        sa.Column("gst_amount", sa.Float(), server_default="0"),
        sa.Column("grand_total", sa.Float(), server_default="0"),
        sa.Column("order_date", sa.Date(), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), server_default="ordered"),
        sa.Column("payment_status", sa.String(20), server_default="pending"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key("fk_procurement_project", "procurement_history", "projects", ["project_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_procurement_vendor", "procurement_history", "vendors", ["vendor_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_procurement_material", "procurement_history", "materials", ["material_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_procurement_project", "procurement_history", ["project_id"])

    # -- Profitability --
    op.create_table(
        "profitability",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Float(), server_default="0"),
        sa.Column("actual_cost", sa.Float(), server_default="0"),
        sa.Column("estimated_revenue", sa.Float(), server_default="0"),
        sa.Column("actual_revenue", sa.Float(), server_default="0"),
        sa.Column("estimated_margin_pct", sa.Float(), server_default="0"),
        sa.Column("actual_margin_pct", sa.Float(), server_default="0"),
        sa.Column("labour_cost_pct", sa.Float(), server_default="0"),
        sa.Column("material_cost_pct", sa.Float(), server_default="0"),
        sa.Column("overhead_cost_pct", sa.Float(), server_default="0"),
        sa.Column("transport_cost_pct", sa.Float(), server_default="0"),
        sa.Column("wastage_cost_pct", sa.Float(), server_default="0"),
        sa.Column("profit_loss", sa.Float(), server_default="0"),
        sa.Column("roe", sa.Float(), server_default="0"),
        sa.Column("currency", sa.String(3), server_default="INR"),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_profitability_project"),
    )
    op.create_foreign_key("fk_profitability_project", "profitability", "projects", ["project_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    """Reverse the full schema upgrade (drop all new tables and columns)."""
    order = [
        "profitability", "procurement_history", "revision_history",
        "project_history", "rate_history", "cost_versions",
        "client_templates", "design_assets", "company_standards",
        "productivity_rates", "wastage_rules", "labour_rates",
        "boq_rules", "drawing_object_types", "users",
    ]
    for table in order:
        op.drop_table(table)

    # Drop new columns from existing tables (reverse order)
    boq_columns = [
        "sort_order", "revision", "approved_at", "approved_by", "approval_status",
        "total_cost", "base_cost", "margin_cost", "overhead_cost", "transport_cost",
        "wastage_cost", "wastage_pct", "rule_id", "is_expanded", "hierarchy_level",
        "parent_id", "code", "updated_at", "deleted_at", "is_deleted",
    ]
    for col in boq_columns:
        op.drop_column("boq_items", col)

    detected_columns = [
        "updated_at", "deleted_at", "is_deleted", "embedding",
        "polyline_json", "parent_id",
    ]
    for col in detected_columns:
        op.drop_column("detected_objects", col)

    vendor_columns = [
        "updated_at", "created_at", "deleted_at", "is_deleted",
        "embedding", "credit_limit", "approval_date", "is_approved",
        "categories_served", "bank_details", "payment_terms", "website", "vendor_code",
    ]
    for col in vendor_columns:
        op.drop_column("vendors", col)

    material_columns = [
        "updated_at", "created_at", "deleted_at", "is_deleted",
        "embedding", "parent_material_id", "has_variants",
        "alternative_material_ids", "tags", "is_active", "vendor_id",
        "moq_description", "cess", "gst_rate", "hsn_code", "subcategory",
    ]
    for col in material_columns:
        op.drop_column("materials", col)

    drawing_columns = [
        "updated_at", "created_at", "deleted_at", "is_deleted",
        "uploaded_by", "error_message", "processed_at", "revision",
        "page_count", "scale", "description", "minio_object_key", "project_id",
    ]
    for col in drawing_columns:
        op.drop_column("drawings", col)

    project_columns = [
        "deleted_at", "is_deleted", "created_by", "currency",
        "po_number", "gst_hst", "site_address", "client_ref",
        "end_date", "start_date", "project_code",
    ]
    for col in project_columns:
        op.drop_column("projects", col)
