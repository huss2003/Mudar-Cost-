"""Pydantic schemas for BOQ (Bill of Quantities) API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BOQLineItemResponse(BaseModel):
    """A single BOQ line item as returned by the API."""

    id: int
    description: str
    material_code: Optional[str] = None
    quantity: float
    unit: str
    wastage_pct: float = 0.0
    total_qty: float
    rate: float
    total: float
    source_object_type: Optional[str] = None
    source_object_id: Optional[int] = None
    trade: Optional[str] = None
    hierarchy_level: int = 0


class BOQTradeGroup(BaseModel):
    """A group of line items under a single trade."""

    trade: str
    items: list[BOQLineItemResponse]
    subtotal: float


class BOQResponse(BaseModel):
    """Complete BOQ response for a project, grouped by trade."""

    project_id: int
    cost_version_id: Optional[int] = None
    version_name: Optional[str] = None
    groups: list[BOQTradeGroup]
    grand_total: float
    currency: str = "INR"


class BOQSummaryRow(BaseModel):
    """A single summary row (one trade or grand total)."""

    trade: str
    item_count: int
    total_qty: float
    subtotal: float


class BOQSummaryResponse(BaseModel):
    """Aggregated BOQ summary with grand total."""

    project_id: int
    cost_version_id: Optional[int] = None
    version_name: Optional[str] = None
    rows: list[BOQSummaryRow]
    grand_total: float
    currency: str = "INR"


class CostVersionResponse(BaseModel):
    """A cost version listed in the versions index."""

    id: int
    version_number: int
    name: Optional[str] = None
    status: str
    grand_total: float
    created_at: Optional[datetime] = None


class ComputeResponse(BaseModel):
    """Returned immediately after dispatching a compute task."""

    job_id: str
    status: str = "computing"
