"""Pydantic schemas for AI Feature API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ======================================================================
# POST /projects/{project_id}/ask
# ======================================================================


class AskRequest(BaseModel):
    """Request body for the natural-language Q&A endpoint."""

    question: str = Field(..., min_length=1, max_length=2000)
    stream: bool = False


class SourceRef(BaseModel):
    """A reference source cited in an AI answer."""

    source: str
    relevance: Optional[str] = None


class AskResponse(BaseModel):
    """Response from the project Q&A endpoint."""

    answer: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    sources: list[str] = []
    is_ai_generated: bool = Field(
        True,
        description="Whether this answer was produced by the AI (vs rule-based fallback)",
    )
    ai_status: str = Field(
        "available",
        description="Status of the AI pipeline: 'available', 'unavailable', or 'degraded'",
    )


# ======================================================================
# POST /projects/{project_id}/missing-boq
# ======================================================================


class MissingBOQItem(BaseModel):
    """A single suggested BOQ item that appears to be missing."""

    category: str
    item_description: str
    estimated_quantity: float
    unit: str = "nos"
    reason: str = ""
    derived_from: Optional[str] = None  # e.g. "DetectedObject type" or "Similar project"


class MissingBOQResponse(BaseModel):
    """Response from the missing-BOQ detection endpoint."""

    suggested_items: list[MissingBOQItem]
    gap_count: int
    analysis_summary: str = ""


# ======================================================================
# POST /projects/{project_id}/anomalies
# ======================================================================


class AnomalyItem(BaseModel):
    """A single detected anomaly."""

    boq_item_id: Optional[int] = None
    description: str
    field: str  # e.g. "rate", "quantity", "material_category"
    expected: str
    actual: str
    deviation_pct: float = 0.0
    severity: str = "medium"  # low, medium, high


class AnomalyResponse(BaseModel):
    """Response from the anomaly detection endpoint."""

    anomalies: list[AnomalyItem]
    anomaly_count: int
    project_health: str = ""  # "healthy", "needs_review", "action_required"


# ======================================================================
# POST /projects/{project_id}/value-engineering
# ======================================================================


class VESuggestion(BaseModel):
    """A single value-engineering suggestion."""

    rank: int
    boq_item_id: int
    description: str
    current_material: Optional[str] = None
    suggested_material: Optional[str] = None
    current_cost: float = 0.0
    suggested_cost: float = 0.0
    savings: float = 0.0
    savings_pct: float = 0.0
    implementation_effort: str = "medium"  # low, medium, high
    risk: str = "low"  # low, medium, high


class VEResponse(BaseModel):
    """Response from the value engineering endpoint."""

    suggestions: list[VESuggestion]
    total_potential_savings: float = 0.0
    suggestion_count: int


# ======================================================================
# POST /projects/{project_id}/duration-predict
# ======================================================================


class TradeDurationBreakdown(BaseModel):
    """Duration estimate for a single trade."""

    trade: str
    total_quantity: float
    unit: str
    output_per_day: float
    crew_size: int
    duration_days: float
    depends_on: list[str] = []


class GanttBar(BaseModel):
    """A single bar in the Gantt chart."""

    trade: str
    start_day: int
    end_day: int
    duration_days: float
    depends_on: list[str] = []


class DurationPredictResponse(BaseModel):
    """Response from the duration prediction endpoint."""

    total_days: int
    trade_breakdown: list[TradeDurationBreakdown]
    gantt_data: list[GanttBar]
    critical_path: list[str]
