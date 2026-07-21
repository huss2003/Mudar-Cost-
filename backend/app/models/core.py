"""Core domain models: User, Project, Drawing."""

import datetime
from typing import Optional

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin


class User(TimestampMixin, SoftDeleteMixin, Base):
    """Application user authenticated via Keycloak OIDC."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sub: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="estimator", server_default="estimator")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    # Relationships
    projects: Mapped[list["Project"]] = relationship(
        foreign_keys="Project.created_by", back_populates="created_by_user"
    )
    drawings_uploaded: Mapped[list["Drawing"]] = relationship(
        foreign_keys="Drawing.uploaded_by", back_populates="uploaded_by_user"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} sub={self.sub!r}>"


class Project(TimestampMixin, SoftDeleteMixin, Base):
    """An estimation project containing drawings, BOQs, and cost data."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client: Mapped[Optional[str]] = mapped_column(String(255))
    project_code: Mapped[Optional[str]] = mapped_column(String(50), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="draft"
    )
    location: Mapped[Optional[str]] = mapped_column(String(255))
    start_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    end_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    client_ref: Mapped[Optional[str]] = mapped_column(String(255))
    site_address: Mapped[Optional[str]] = mapped_column(Text)
    gst_hst: Mapped[Optional[str]] = mapped_column(String(50))
    po_number: Mapped[Optional[str]] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")

    # Embedding for semantic search
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(384))

    # Cost summary columns (from 0001)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    total_labour: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    total_materials: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    total_transport: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    total_overhead: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    total_margin: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    grand_total: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")

    # FK
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    # Relationships
    created_by_user: Mapped[Optional["User"]] = relationship(
        foreign_keys=[created_by], back_populates="projects"
    )
    drawings: Mapped[list["Drawing"]] = relationship(back_populates="project")
    boq_items: Mapped[list["BOQItem"]] = relationship(back_populates="project")
    cost_versions: Mapped[list["CostVersion"]] = relationship(back_populates="project")
    project_history: Mapped[list["ProjectHistory"]] = relationship(back_populates="project")
    revisions: Mapped[list["RevisionHistory"]] = relationship(back_populates="project")
    procurements: Mapped[list["ProcurementHistory"]] = relationship(back_populates="project")
    profitability: Mapped[Optional["Profitability"]] = relationship(
        back_populates="project", uselist=False
    )
    export_records: Mapped[list["ExportRecord"]] = relationship(back_populates="project")

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name!r}>"


class Drawing(TimestampMixin, SoftDeleteMixin, Base):
    """An uploaded CAD drawing / PDF associated with a project."""

    __tablename__ = "drawings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(512))  # legacy from 0001
    minio_object_key: Mapped[Optional[str]] = mapped_column(String(512))
    file_size_bytes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    sha256_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="SHA-256 hex digest for dedup"
    )
    upload_date: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="uploaded"
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    scale: Mapped[Optional[str]] = mapped_column(String(50))
    page_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    processed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Legacy columns from 0001
    user_id: Mapped[Optional[str]] = mapped_column(String(255))
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(512))

    # FKs
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    uploaded_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="drawings")
    uploaded_by_user: Mapped[Optional["User"]] = relationship(
        foreign_keys=[uploaded_by], back_populates="drawings_uploaded"
    )
    detected_objects: Mapped[list["DetectedObject"]] = relationship(
        back_populates="drawing"
    )

    def __repr__(self) -> str:
        return f"<Drawing id={self.id} filename={self.filename!r}>"
