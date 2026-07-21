"""Shared Pydantic schemas for the Drawing Intelligence detection pipeline.

Every parser (CAD, PDF) emits this normalized format, and the normalizer
consumes it to dedupe, merge, and write into Postgres detected_objects.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Input schemas
# =============================================================================

class DetectedObjectCreate(BaseModel):
    """A single detected object from a CAD or PDF parse result.

    All coordinate values are in millimetres in the drawing's native CS.
    """
    object_type: str = Field(
        ...,
        description="Normalised type: wall, glass, partition, cabin, meeting_room, "
                    "door, window, ceiling, floor, column, furniture, "
                    "electrical_symbol, hvac_symbol, stair, beam, duct, pipe, other",
    )
    label: Optional[str] = Field(None, description="Text label / room name if available")
    length: Optional[float] = Field(None, description="Object length in mm")
    width: Optional[float] = Field(None, description="Object width / thickness in mm")
    area: Optional[float] = Field(None, description="Computed area in sqmm or sqm (see unit)")
    area_unit: str = Field("sqmm", description="sqmm or sqm")
    height: Optional[float] = Field(None, description="Height / elevation in mm")
    thickness: Optional[float] = Field(None, description="Wall / panel thickness in mm")
    location_x: Optional[float] = Field(None, description="Centre X in mm")
    location_y: Optional[float] = Field(None, description="Centre Y in mm")
    elevation: Optional[float] = Field(None, description="Elevation / Z in mm")
    layer: Optional[str] = Field(None, description="CAD layer name or PDF grouping")
    rotation: Optional[float] = Field(None, description="Rotation in degrees")
    raw_attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Source-specific extra attributes (block name, colour, lineweight, etc.)",
    )
    bbox_coords: Optional[List[float]] = Field(
        None,
        description="Bounding box [x1, y1, x2, y2] in mm",
    )
    polyline_json: Optional[List[dict[str, Any]]] = Field(
        None,
        description="Ordered list of vertex dicts [{x, y, bulge?}, ...] for the outline",
    )
    confidence: float = Field(1.0, ge=0, le=1, description="Parser confidence 0-1")
    source: str = Field("cad", description="Source parser: 'cad' or 'pdf'")
    is_ai_generated: Optional[bool] = Field(
        None,
        description="Whether this object was produced by the AI vision pipeline",
    )
    ai_status: Optional[str] = Field(
        None,
        description="Status of the AI pipeline: 'available', 'unavailable', 'degraded', or None",
    )
    parent_id: Optional[int] = Field(
        None,
        description="Hierarchical parent (e.g. wall that a door belongs to)",
    )


class DetectionResult(BaseModel):
    """Complete parse result returned by a Celery task."""
    drawing_id: int
    status: str = "completed"
    objects: List[DetectedObjectCreate] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    processing_time_ms: Optional[float] = None
    source_format: Optional[str] = None  # "dxf", "dwg", "pdf"


# =============================================================================
# API response schemas
# =============================================================================

class DrawingUploadResponse(BaseModel):
    """Returned immediately after a file upload."""
    drawing_id: int
    filename: str
    sha256_hash: Optional[str] = Field(
        None, description="SHA-256 hex digest of file content for dedup"
    )
    status: str = "uploaded"
    job_id: Optional[str] = None  # Celery task ID
    routing_hint: Optional[str] = Field(
        None, description="Processing route: cad_parser, ai_vision, or existing"
    )
    message: str = "File uploaded. Processing started."


class DrawingStatusResponse(BaseModel):
    """Status of a drawing after processing."""
    drawing_id: int
    filename: str
    status: str  # uploaded, processing, analyzed, failed
    object_count: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None


class DrawingObjectResponse(BaseModel):
    """A detected object as returned by the API."""
    id: int
    drawing_id: int
    object_type: str
    label: Optional[str] = None
    length: Optional[float] = None
    width: Optional[float] = None
    area: Optional[float] = None
    height: Optional[float] = None
    thickness: Optional[float] = None
    location_x: Optional[float] = None
    location_y: Optional[float] = None
    layer: Optional[str] = None
    confidence: Optional[float] = None
    bbox_coords: Optional[List[float]] = None


class ObjectTypeSummary(BaseModel):
    """Object counts grouped by type (for dashboards)."""
    object_type: str
    count: int
    total_area: Optional[float] = None


# =============================================================================
# Normalizer internal schemas
# =============================================================================

class ObjectMergeGroup(BaseModel):
    """Group of candidate objects that may represent the same real entity."""
    ref_ids: List[int]
    object_type: str
    iou: float  # Intersection-over-Union
    merged: Optional[DetectedObjectCreate] = None
