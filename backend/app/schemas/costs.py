"""Pydantic schemas for cost engine API responses."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CostBreakdownResponse(BaseModel):
    """Detailed cost breakdown for a single BOQ line item."""

    item_id: int
    description: str
    quantity: float
    unit: str
    rate: float
    material_cost: float
    labour_cost: float
    transport_cost: float
    overhead_cost: float
    margin_cost: float
    subtotal: float
    discount_amount: float
    gst_amount: float
    grand_total: float


class CostVersionSummaryResponse(BaseModel):
    """Aggregated cost version summary returned by the API."""

    cost_version_id: int
    version_number: int
    total_materials: float
    total_labour: float
    total_wastage: float
    total_transport: float
    total_overhead: float
    total_margin: float
    total_before_gst: float
    total_discount: float
    total_gst: float
    grand_total: float
    currency: str = "INR"
    item_count: int


class TradeCostGroupResponse(BaseModel):
    """Cost subtotals grouped by trade."""

    trade: str
    item_count: int
    total_materials: float
    total_labour: float
    total_wastage: float
    total_transport: float
    total_overhead: float
    total_margin: float
    subtotal: float


class CostVersionDetailResponse(BaseModel):
    """Full cost version detail with trade groups and line items."""

    cost_version_id: int
    version_number: int
    name: Optional[str] = None
    status: str
    currency: str = "INR"
    trade_groups: list[TradeCostGroupResponse]
    items: list[CostBreakdownResponse]
    total_materials: float
    total_labour: float
    total_wastage: float
    total_transport: float
    total_overhead: float
    total_margin: float
    total_before_gst: float
    total_discount: float
    total_gst: float
    grand_total: float
    item_count: int
