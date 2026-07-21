"""Asset library and client template models."""

import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Float,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin


class DesignAsset(TimestampMixin, SoftDeleteMixin, Base):
    """A reusable design asset (3D model, texture, material swatch, etc.)."""

    __tablename__ = "design_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100))
    tags: Mapped[Optional[dict]] = mapped_column(JSON)
    minio_object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    thumbnail_key: Mapped[Optional[str]] = mapped_column(String(512))
    file_format: Mapped[Optional[str]] = mapped_column(String(20))
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    asset_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSON)
    source: Mapped[Optional[str]] = mapped_column(String(100))
    license: Mapped[Optional[str]] = mapped_column(String(100))
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    def __repr__(self) -> str:
        return f"<DesignAsset id={self.id} name={self.name!r}>"


class ClientTemplate(TimestampMixin, SoftDeleteMixin, Base):
    """Pre-built BOQ templates per client type."""

    __tablename__ = "client_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_type: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    template_json: Mapped[Optional[dict]] = mapped_column(JSON)
    default_markup_pct: Mapped[float] = mapped_column(
        Float, default=15, server_default="15"
    )
    default_margin_pct: Mapped[float] = mapped_column(
        Float, default=10, server_default="10"
    )
    sections: Mapped[Optional[dict]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    def __repr__(self) -> str:
        return f"<ClientTemplate id={self.id} name={self.name!r}>"
