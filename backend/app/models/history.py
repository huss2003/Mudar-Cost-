"""History & audit trail models: RateHistory, ProjectHistory, RevisionHistory,
ProcurementHistory, Profitability."""

import datetime
from typing import Optional

from sqlalchemy import (
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


class RateHistory(TimestampMixin, Base):
    """Tracks changes to material, labour, or vendor rates over time."""

    __tablename__ = "rate_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reference_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "material", "labour", "vendor"
    reference_id: Mapped[int] = mapped_column(Integer, nullable=False)
    old_rate: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    new_rate: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    old_gst: Mapped[Optional[float]] = mapped_column(Float)
    new_gst: Mapped[Optional[float]] = mapped_column(Float)
    change_reason: Mapped[Optional[str]] = mapped_column(String(255))
    changed_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    effective_date: Mapped[Optional[datetime.date]] = mapped_column(Date)

    def __repr__(self) -> str:
        return (
            f"<RateHistory id={self.id} type={self.reference_type!r}"
            f" ref={self.reference_id}>"
        )


class ProjectHistory(TimestampMixin, Base):
    """Audit trail of significant changes made to a project."""

    __tablename__ = "project_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    field_changed: Mapped[Optional[str]] = mapped_column(String(100))
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    change_type: Mapped[Optional[str]] = mapped_column(String(50))
    changed_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="project_history")

    def __repr__(self) -> str:
        return f"<ProjectHistory id={self.id} project={self.project_id}>"


class RevisionHistory(TimestampMixin, Base):
    """Tracks revisions to BOQ items, drawings, cost versions, and rates."""

    __tablename__ = "revision_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_type: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # "boq", "drawing", "cost", "rate"
    reference_type: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # "boq_item", "drawing", "cost_version"
    reference_id: Mapped[Optional[int]] = mapped_column(Integer)
    change_summary: Mapped[Optional[str]] = mapped_column(Text)
    old_value: Mapped[Optional[dict]] = mapped_column(JSON)
    new_value: Mapped[Optional[dict]] = mapped_column(JSON)
    reason: Mapped[Optional[str]] = mapped_column(Text)

    approved_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="revisions")

    def __repr__(self) -> str:
        return (
            f"<RevisionHistory id={self.id} project={self.project_id}"
            f" rev={self.revision_number}>"
        )


class ProcurementHistory(TimestampMixin, SoftDeleteMixin, Base):
    """Procurement / purchase order records linked to projects."""

    __tablename__ = "procurement_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    po_number: Mapped[Optional[str]] = mapped_column(String(100))
    vendor_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("vendors.id"), nullable=False
    )
    material_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("materials.id"), nullable=True
    )
    quantity: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    unit_rate: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    total_amount: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    gst_amount: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    grand_total: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    order_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    delivery_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(20), default="ordered", server_default="ordered"
    )
    payment_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="procurements")

    def __repr__(self) -> str:
        return f"<ProcurementHistory id={self.id} po={self.po_number!r}>"


class Profitability(TimestampMixin, Base):
    """Profitability analysis snapshot for a project (one per project)."""

    __tablename__ = "profitability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), unique=True, nullable=False
    )
    estimated_cost: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    actual_cost: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    estimated_revenue: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    actual_revenue: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    estimated_margin_pct: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    actual_margin_pct: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    labour_cost_pct: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    material_cost_pct: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    overhead_cost_pct: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    transport_cost_pct: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    wastage_cost_pct: Mapped[float] = mapped_column(
        Float, default=0, server_default="0"
    )
    profit_loss: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    roe: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    currency: Mapped[str] = mapped_column(
        String(3), default="INR", server_default="INR"
    )
    period_start: Mapped[Optional[datetime.date]] = mapped_column(Date)
    period_end: Mapped[Optional[datetime.date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="profitability")

    def __repr__(self) -> str:
        return f"<Profitability id={self.id} project={self.project_id}>"


class ExportRecord(TimestampMixin, Base):
    """Tracks generated export files (XLSX, PDF) with MinIO storage."""

    __tablename__ = "export_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    export_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "boq_xlsx", "proposal_pdf", "purchase_list", "client_presentation"
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )  # pending, processing, completed, failed
    minio_key: Mapped[Optional[str]] = mapped_column(String(512))
    filename: Mapped[Optional[str]] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="export_records")

    def __repr__(self) -> str:
        return (
            f"<ExportRecord id={self.id} project={self.project_id}"
            f" type={self.export_type!r} status={self.status!r}>"
        )
