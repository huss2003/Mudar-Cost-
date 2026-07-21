"""Pydantic schemas for version history API.

Version listing, full breakdown, diff responses, rate history.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class VersionListItem(BaseModel):
    """A cost version listed in the versions index."""

    id: int
    version_number: int
    name: str
    status: str
    grand_total: float
    currency: str
    item_count: int
    created_at: datetime


class DiffLineItem(BaseModel):
    """An item present only in one of the two compared versions."""

    id: int
    description: str
    quantity: float
    unit: str
    rate: float
    total: float
    trade: Optional[str] = None


class VersionDiffItem(BaseModel):
    """An item that changed between two versions."""

    description: str
    old_quantity: float
    new_quantity: float
    old_rate: float
    new_rate: float
    old_total: float
    new_total: float
    delta: float


class VersionDiffResponse(BaseModel):
    """Result of diffing two cost versions."""

    version_a_id: int
    version_b_id: int
    items_changed: list[VersionDiffItem]
    items_added: list[DiffLineItem]
    items_removed: list[DiffLineItem]
    total_delta: float
    material_delta: float
    labour_delta: float
    gst_delta: float


class VersionBreakdownItem(BaseModel):
    """A single item in a version breakdown."""

    id: int
    description: str
    quantity: float
    unit: str
    rate: float
    total: float
    base_cost: float
    wastage_pct: float
    wastage_cost: float
    transport_cost: float
    overhead_cost: float
    margin_cost: float
    total_cost: float
    trade: Optional[str] = None


class VersionTradeGroup(BaseModel):
    """A group of items in a version breakdown under one trade."""

    trade: str
    items: list[VersionBreakdownItem]
    subtotal: float


class VersionBreakdownResponse(BaseModel):
    """Full breakdown of a single cost version."""

    version_id: int
    version_number: int
    name: Optional[str] = None
    status: str
    currency: str
    groups: list[VersionTradeGroup]
    grand_total: float
    total_materials: float
    total_labour: float
    total_wastage: float
    total_transport: float
    total_overhead: float
    total_margin: float


class RateHistoryResponse(BaseModel):
    """A single rate change record."""

    id: int
    reference_type: str
    reference_id: int
    old_rate: float
    new_rate: float
    change_reason: Optional[str] = None
    changed_by: int
    created_at: datetime
