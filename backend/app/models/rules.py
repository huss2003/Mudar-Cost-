"""Rule models: BOQRule, WastageRule, ProductivityRate, CompanyStandard."""

import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin


class BOQRule(TimestampMixin, SoftDeleteMixin, Base):
    """A rule that generates BOQ sub-items from a detected object type."""

    __tablename__ = "boq_rules"

    __table_args__ = (UniqueConstraint("object_type", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    object_type: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    trade: Mapped[Optional[str]] = mapped_column(String(50))
    formula: Mapped[Optional[str]] = mapped_column(Text)
    sub_items: Mapped[Optional[list]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    def __repr__(self) -> str:
        return f"<BOQRule id={self.id} type={self.object_type!r} v{self.version}>"


class WastageRule(TimestampMixin, SoftDeleteMixin, Base):
    """Standard wastage percentages by material category."""

    __tablename__ = "wastage_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_category: Mapped[str] = mapped_column(String(100), nullable=False)
    material_subcategory: Mapped[Optional[str]] = mapped_column(String(100))
    wastage_pct: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    description: Mapped[Optional[str]] = mapped_column(String(255))
    applicable_to: Mapped[str] = mapped_column(
        String(50), default="material", server_default="material"
    )
    region: Mapped[Optional[str]] = mapped_column(String(100))
    is_mandatory: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    def __repr__(self) -> str:
        return (
            f"<WastageRule id={self.id} category={self.material_category!r}>"
        )


class ProductivityRate(TimestampMixin, SoftDeleteMixin, Base):
    """Expected daily output rates for labour activities."""

    __tablename__ = "productivity_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade: Mapped[str] = mapped_column(String(50), nullable=False)
    activity: Mapped[Optional[str]] = mapped_column(String(255))
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    output_per_day: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    crew_size: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    crew_composition: Mapped[Optional[dict]] = mapped_column(JSON)
    equipment_needed: Mapped[Optional[dict]] = mapped_column(JSON)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<ProductivityRate id={self.id} trade={self.trade!r}>"


class CompanyStandard(TimestampMixin, SoftDeleteMixin, Base):
    """Company-wide standard values for design & estimation parameters."""

    __tablename__ = "company_standards"

    __table_args__ = (UniqueConstraint("category", "name", "region"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[Optional[str]] = mapped_column(String(255))
    value_float: Mapped[Optional[float]] = mapped_column(Float)
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_global: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    region: Mapped[Optional[str]] = mapped_column(String(100))

    def __repr__(self) -> str:
        return f"<CompanyStandard id={self.id} {self.category}:{self.name!r}>"
