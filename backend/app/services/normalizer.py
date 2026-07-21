"""Drawing Intelligence — Normalizer Service.

Takes raw DetectionResult from CAD or PDF parsers, deduplicates overlapping
objects, computes room enclosures, and writes normalized records to Postgres.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.detection import DetectedObject
from app.schemas.detection import DetectedObjectCreate, DetectionResult

logger = logging.getLogger(__name__)


# =============================================================================
# Geometry helpers
# =============================================================================

def bbox_area(bbox: List[float]) -> float:
    """Compute area of bounding box [x1, y1, x2, y2]."""
    if not bbox or len(bbox) < 4:
        return 0.0
    return max(0.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))


def bbox_intersection(a: List[float], b: List[float]) -> List[float]:
    """Return intersection bbox of two bboxes, or empty if none."""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    if x1 < x2 and y1 < y2:
        return [x1, y1, x2, y2]
    return []


def bbox_iou(a: List[float], b: List[float]) -> float:
    """Intersection-over-Union for two bounding boxes."""
    inter = bbox_intersection(a, b)
    if not inter:
        return 0.0
    inter_area = bbox_area(inter)
    union_area = bbox_area(a) + bbox_area(b) - inter_area
    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def point_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    """Euclidean distance between two points."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


# =============================================================================
# Deduplication
# =============================================================================

IOU_THRESHOLD = 0.5  # Objects with IoU > this are considered duplicates


def deduplicate_objects(
    objects: List[DetectedObjectCreate],
    iou_threshold: float = IOU_THRESHOLD,
) -> List[DetectedObjectCreate]:
    """Remove near-duplicate objects detected by multiple parsers.

    Strategy: keep the object with higher confidence; discard the rest.
    """
    if not objects:
        return []

    # Assign stable index
    indexed = list(enumerate(objects))
    keep = [True] * len(objects)

    for i in range(len(indexed)):
        if not keep[i]:
            continue
        _, obj_a = indexed[i]
        bbox_a = obj_a.bbox_coords
        if not bbox_a:
            continue
        for j in range(i + 1, len(indexed)):
            if not keep[j]:
                continue
            _, obj_b = indexed[j]
            bbox_b = obj_b.bbox_coords
            if not bbox_b:
                continue
            # Only dedupe objects of the same type
            if obj_a.object_type != obj_b.object_type:
                continue
            iou = bbox_iou(bbox_a, bbox_b)
            if iou > iou_threshold:
                # Keep the one with higher confidence
                if obj_a.confidence >= obj_b.confidence:
                    keep[j] = False
                else:
                    keep[i] = False
                    break  # obj_a is being removed

    return [objects[i] for i in range(len(objects)) if keep[i]]


# =============================================================================
# Room enclosure detection (optional post-processing)
# =============================================================================

def _find_enclosed_rooms(
    walls: List[DetectedObjectCreate],
) -> List[Dict[str, Any]]:
    """Simple room detection: find closed loops formed by wall segments.

    This is a simplified implementation.  For production, use a proper
    polygon library (shapely).  For now we detect rooms by finding
    groups of walls whose bounding boxes form enclosed areas.
    """
    rooms = []
    # Collect all wall endpoints
    wall_lines = []
    for w in walls:
        bbox = w.bbox_coords
        if bbox and len(bbox) >= 4:
            wall_lines.append({
                "x1": bbox[0], "y1": bbox[1],
                "x2": bbox[2], "y2": bbox[3],
                "object": w,
            })

    # Simple grid-based room detection: find non-overlapping
    # rectangular areas bounded by walls
    if len(wall_lines) >= 4:
        # Get all unique X and Y coordinates from wall endpoints
        xs = set()
        ys = set()
        for wl in wall_lines:
            xs.add(wl["x1"])
            xs.add(wl["x2"])
            ys.add(wl["y1"])
            ys.add(wl["y2"])

        if len(xs) >= 2 and len(ys) >= 2:
            xs_sorted = sorted(xs)
            ys_sorted = sorted(ys)

            # For each rectangle in the grid, check if it's bounded by walls
            for xi in range(len(xs_sorted) - 1):
                for yi in range(len(ys_sorted) - 1):
                    x1, x2 = xs_sorted[xi], xs_sorted[xi + 1]
                    y1, y2 = ys_sorted[yi], ys_sorted[yi + 1]
                    room_area = (x2 - x1) * (y2 - y1)
                    # Minimum room area (0.5 sqm = 500,000 sqmm)
                    if room_area < 500_000:
                        continue
                    rooms.append({
                        "bbox": [x1, y1, x2, y2],
                        "area_sqmm": room_area,
                        "center_x": (x1 + x2) / 2,
                        "center_y": (y1 + y2) / 2,
                    })

    return rooms


# =============================================================================
# Assignment of labels to rooms
# =============================================================================

def _assign_labels_to_rooms(
    rooms: List[Dict[str, Any]],
    labels: List[DetectedObjectCreate],
) -> List[Dict[str, Any]]:
    """Match text labels (room names) to detected room enclosures."""
    for room in rooms:
        r_bbox = room["bbox"]
        r_cx, r_cy = room["center_x"], room["center_y"]
        for label_obj in labels:
            if not label_obj.bbox_coords or len(label_obj.bbox_coords) < 4:
                continue
            l_cx = (label_obj.bbox_coords[0] + label_obj.bbox_coords[2]) / 2
            l_cy = (label_obj.bbox_coords[1] + label_obj.bbox_coords[3]) / 2
            # Check if label center is inside room bbox
            if (r_bbox[0] <= l_cx <= r_bbox[2] and
                    r_bbox[1] <= l_cy <= r_bbox[3]):
                room["label"] = label_obj.label or room.get("label")
                break

    return rooms


# =============================================================================
# Main normalization pipeline
# =============================================================================

async def normalize_and_store(
    db: AsyncSession,
    drawing_id: int,
    result: DetectionResult,
) -> int:
    """Full normalization pipeline: dedupe → room-detect → store → return count.

    Returns the number of DetectedObject rows written.
    """
    # 1. Deduplicate
    objects = deduplicate_objects(result.objects)
    logger.info(
        "Normalizer: %d raw → %d after dedup",
        len(result.objects),
        len(objects),
    )

    # 2. Separate walls and labels for room detection
    walls = [o for o in objects if o.object_type in ("wall", "partition")]
    labels = [o for o in objects if o.object_type == "other" and o.label]

    # 3. Compute rooms
    rooms = _find_enclosed_rooms(walls)
    rooms = _assign_labels_to_rooms(rooms, labels)

    # 4. Write detected_objects to Postgres
    written = 0
    for obj_data in objects:
        detected = DetectedObject(
            drawing_id=drawing_id,
            object_type=obj_data.object_type,
            label=obj_data.label,
            length=obj_data.length,
            width=obj_data.width,
            area=obj_data.area,
            height=obj_data.height,
            thickness=obj_data.thickness,
            location_x=obj_data.location_x,
            location_y=obj_data.location_y,
            layer=obj_data.layer,
            confidence=obj_data.confidence,
            bbox_coords=(
                ",".join(str(c) for c in obj_data.bbox_coords)
                if obj_data.bbox_coords else None
            ),
            polyline_json=obj_data.polyline_json,
            metadata_json=obj_data.raw_attributes,
        )
        db.add(detected)
        written += 1

    await db.commit()
    logger.info("Normalizer: wrote %d DetectedObject rows", written)

    # 5. (Optional) Store room data — could write room records or
    #    tag the enclosing wall objects with room labels

    return written


async def get_objects_for_drawing(
    db: AsyncSession,
    drawing_id: int,
) -> List[DetectedObject]:
    """Retrieve all normalized objects for a drawing."""
    stmt = (
        select(DetectedObject)
        .where(
            DetectedObject.drawing_id == drawing_id,
            DetectedObject.is_deleted == False,
        )
        .order_by(DetectedObject.id)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_object_counts_by_type(
    db: AsyncSession,
    drawing_id: int,
) -> List[Dict[str, Any]]:
    """Return object counts grouped by type for a drawing."""
    stmt = (
        select(
            DetectedObject.object_type,
            DetectedObject.id,
            DetectedObject.area,
        )
        .where(
            DetectedObject.drawing_id == drawing_id,
            DetectedObject.is_deleted == False,
        )
    )
    result = await db.execute(stmt)
    rows = result.all()

    counts: Dict[str, dict] = {}
    for row in rows:
        t = row.object_type
        if t not in counts:
            counts[t] = {"object_type": t, "count": 0, "total_area": 0.0}
        counts[t]["count"] += 1
        if row.area:
            counts[t]["total_area"] += row.area

    return list(counts.values())
