"""Reference & catalogue models: DrawingObjectType, Material, Vendor, LabourRate."""

import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin


class DrawingObjectType(TimestampMixin, SoftDeleteMixin, Base):
    """Catalogue of recognised object types for AI detection & BOQ rules."""

    __tablename__ = "drawing_object_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    category: Mapped[Optional[str]] = mapped_column(String(100))
    default_unit: Mapped[str] = mapped_column(
        String(20), default="sqm", server_default="sqm"
    )
    icon: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    attributes_schema: Mapped[Optional[dict]] = mapped_column(JSON)
    detection_prompt: Mapped[Optional[str]] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<DrawingObjectType id={self.id} name={self.name!r}>"


class Material(TimestampMixin, SoftDeleteMixin, Base):
    """Catalogue of construction/finishing materials with pricing."""

    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    subcategory: Mapped[Optional[str]] = mapped_column(String(100))
    sku: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    hsn_code: Mapped[Optional[str]] = mapped_column(String(20))
    gst_rate: Mapped[float] = mapped_column(Float, default=18, server_default="18")
    cess: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    rate: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    unit: Mapped[str] = mapped_column(String(50), nullable=False, server_default="nos")

    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    warranty: Mapped[Optional[str]] = mapped_column(String(255))
    fire_rating: Mapped[Optional[str]] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)
    min_order_qty: Mapped[Optional[float]] = mapped_column(
        Float, server_default="1"
    )
    moq_description: Mapped[Optional[str]] = mapped_column(String(255))
    lead_time_days: Mapped[Optional[int]] = mapped_column(
        Integer, server_default="7"
    )

    vendor_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("vendors.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    tags: Mapped[Optional[dict]] = mapped_column(JSON)
    alternative_material_ids: Mapped[Optional[list]] = mapped_column(JSON)
    has_variants: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    parent_material_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("materials.id"), nullable=True
    )

    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(384))

    # Relationships
    vendor: Mapped[Optional["Vendor"]] = relationship(back_populates="materials")
    parent_material: Mapped[Optional["Material"]] = relationship(
        back_populates="variants",
        foreign_keys=[parent_material_id],
        remote_side="Material.id",
    )
    variants: Mapped[list["Material"]] = relationship(
        back_populates="parent_material",
        foreign_keys=[parent_material_id],
        remote_side="Material.id",
    )

    def __repr__(self) -> str:
        return f"<Material id={self.id} name={self.name!r}>"


class Vendor(TimestampMixin, SoftDeleteMixin, Base):
    """Vendor / supplier information."""

    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor_code: Mapped[Optional[str]] = mapped_column(String(50), unique=True)
    contact_person: Mapped[Optional[str]] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    website: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    address: Mapped[Optional[str]] = mapped_column(Text)
    gst: Mapped[Optional[str]] = mapped_column(String(50))
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255))
    bank_details: Mapped[Optional[str]] = mapped_column(Text)
    delivery_time_days: Mapped[Optional[int]] = mapped_column(
        Integer, server_default="7"
    )
    moq: Mapped[Optional[float]] = mapped_column(Float, server_default="1")
    rating: Mapped[Optional[float]] = mapped_column(Float)
    categories_served: Mapped[Optional[dict]] = mapped_column(JSON)
    is_approved: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    approval_date: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    credit_limit: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    notes: Mapped[Optional[str]] = mapped_column(Text)

    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(384))

    # Relationships
    materials: Mapped[list["Material"]] = relationship(back_populates="vendor")

    def __repr__(self) -> str:
        return f"<Vendor id={self.id} name={self.name!r}>"


class LabourRate(TimestampMixin, SoftDeleteMixin, Base):
    """Standard labour rates by trade, skill level, and city category."""

    __tablename__ = "labour_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    skill_level: Mapped[Optional[str]] = mapped_column(String(50))
    unit: Mapped[str] = mapped_column(String(20), default="day", server_default="day")
    basic_rate: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    hra: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    conveyance: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    food_allowance: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    insurance: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    other_allowances: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    total_rate: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    effective_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    city_category: Mapped[Optional[str]] = mapped_column(String(20))
    is_union_rate: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<LabourRate id={self.id} trade={self.trade!r}>"
