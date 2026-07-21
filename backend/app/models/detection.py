"""Detection & estimation models: DetectedObject, BOQItem, CostVersion."""

import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin


class DetectedObject(TimestampMixin, SoftDeleteMixin, Base):
    """An object detected/recognised inside a drawing (wall, door, window, …)."""

    __tablename__ = "detected_objects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drawing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("detected_objects.id"), nullable=True
    )
    object_type: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(255))
    length: Mapped[Optional[float]] = mapped_column(Float)
    width: Mapped[Optional[float]] = mapped_column(Float)
    area: Mapped[Optional[float]] = mapped_column(Float)
    height: Mapped[Optional[float]] = mapped_column(Float)
    thickness: Mapped[Optional[float]] = mapped_column(Float)
    layer: Mapped[Optional[str]] = mapped_column(String(100))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    bbox_coords: Mapped[Optional[str]] = mapped_column(String(500))
    polyline_json: Mapped[Optional[str]] = mapped_column(Text)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(384))

    # Relationships
    drawing: Mapped["Drawing"] = relationship(back_populates="detected_objects")
    children: Mapped[list["DetectedObject"]] = relationship(
        back_populates="parent",
        foreign_keys=[parent_id],
        remote_side="DetectedObject.id",
    )
    parent: Mapped[Optional["DetectedObject"]] = relationship(
        back_populates="children",
        foreign_keys=[parent_id],
        remote_side="DetectedObject.id",
    )
    boq_items: Mapped[list["BOQItem"]] = relationship(back_populates="detected_object")

    def __repr__(self) -> str:
        return f"<DetectedObject id={self.id} type={self.object_type!r}>"


class BOQItem(TimestampMixin, SoftDeleteMixin, Base):
    """A line item in the Bill of Quantities for a project."""

    __tablename__ = "boq_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[Optional[str]] = mapped_column(String(50))
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("boq_items.id"), nullable=True
    )
    hierarchy_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_expanded: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    drawing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False
    )
    object_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("detected_objects.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    rule_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("boq_rules.id"), nullable=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100))

    # Quantities
    quantity: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    unit: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="nos"
    )

    # Rates
    rate: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    labour_rate: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )
    transport_rate: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )
    overhead_rate: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )
    margin_rate: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )

    # Costs
    wastage_pct: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    wastage_cost: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    transport_cost: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    overhead_cost: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    margin_cost: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    base_cost: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    total: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    total_cost: Mapped[float] = mapped_column(Float, default=0, server_default="0")

    # Cost percentages
    discount_pct: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    transport_pct: Mapped[float] = mapped_column(Float, default=5, server_default="5")
    overhead_pct: Mapped[float] = mapped_column(Float, default=10, server_default="10")
    margin_pct: Mapped[float] = mapped_column(Float, default=15, server_default="15")
    gst_rate: Mapped[float] = mapped_column(Float, default=18, server_default="18")

    # References
    material_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("materials.id", ondelete="SET NULL"), nullable=True
    )
    material_name: Mapped[Optional[str]] = mapped_column(String(255))
    vendor_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True
    )

    # Approval
    approval_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    approved_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Legacy
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Embedding for semantic search
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(384))

    # Relationships
    detected_object: Mapped[Optional["DetectedObject"]] = relationship(
        back_populates="boq_items"
    )
    project: Mapped[Optional["Project"]] = relationship(back_populates="boq_items")
    parent_item: Mapped[Optional["BOQItem"]] = relationship(
        back_populates="children",
        foreign_keys=[parent_id],
        remote_side="BOQItem.id",
    )
    children: Mapped[list["BOQItem"]] = relationship(
        back_populates="parent_item",
        foreign_keys=[parent_id],
        remote_side="BOQItem.id",
    )

    def __repr__(self) -> str:
        return f"<BOQItem id={self.id} desc={self.description[:40]!r}>"


class CostVersion(TimestampMixin, SoftDeleteMixin, Base):
    """A versioned cost estimate snapshot for a project."""

    __tablename__ = "cost_versions"

    __table_args__ = (UniqueConstraint("project_id", "version_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)

    total_cost: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    total_materials: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    total_labour: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    total_wastage: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    total_transport: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    total_overhead: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    total_margin: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    grand_total: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    currency: Mapped[str] = mapped_column(
        String(3), default="INR", server_default="INR"
    )

    status: Mapped[str] = mapped_column(
        String(20), default="draft", server_default="draft"
    )

    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    approved_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="cost_versions")

    def __repr__(self) -> str:
        return (
            f"<CostVersion id={self.id} project={self.project_id}"
            f" v{self.version_number}>"
        )
