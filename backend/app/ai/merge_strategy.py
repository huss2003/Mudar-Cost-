"""Merge strategy: combine rule-based (CAD/PDF) and AI (MiMo) detection results.

The strategy applies different handling based on IoU overlap between
rule-based and AI-detected objects:

- **Case A (IoU >= 0.4)**: Same object — keep rule-based geometry
  (measured, not hallucinated). If AI has a more specific label, use it.
  Confidence = max(rule.confidence, ai.confidence × 0.9).

- **Case B (0.2 <= IoU < 0.4)**: Partial overlap — discounted AI addition
  with rule-based geometry. Confidence = ai.confidence × 0.7.

- **Case C (IoU < 0.2)**: AI-only detection — heavily discounted.
  Confidence = ai.confidence × 0.6.

- **Case D**: Rule-based with no AI overlap — kept as-is.

Objects with final confidence < 0.2 are removed.  A final dedup pass
removes near-duplicates (IoU > 0.5, same type) keeping the higher
confidence object.
"""

from __future__ import annotations

import logging
from typing import List

from app.schemas.detection import DetectedObjectCreate

logger = logging.getLogger(__name__)

# =============================================================================
# Thresholds
# =============================================================================

IOU_SAME = 0.4          # Case A — same object
IOU_PARTIAL = 0.2       # Case B — partial overlap
CONFIDENCE_FLOOR = 0.2  # Remove objects below this
FINAL_DUP_IOU = 0.5     # Final dedup threshold for same-type objects

# =============================================================================
# Geometry helpers (self-contained copy so merge_strategy is independently
# testable without importing from normalizer)
# =============================================================================


def bbox_area(bbox: List[float]) -> float:
    """Compute area of bounding box ``[x1, y1, x2, y2]``."""
    if not bbox or len(bbox) < 4:
        return 0.0
    return max(0.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))


def bbox_intersection(a: List[float], b: List[float]) -> List[float]:
    """Return intersection bbox of two bboxes, or empty list if none."""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    if x1 < x2 and y1 < y2:
        return [x1, y1, x2, y2]
    return []


def bbox_iou(a: List[float], b: List[float]) -> float:
    """Intersection-over-Union for two bounding boxes ``[x1, y1, x2, y2]``."""
    inter = bbox_intersection(a, b)
    if not inter:
        return 0.0
    inter_area = bbox_area(inter)
    union_area = bbox_area(a) + bbox_area(b) - inter_area
    if union_area <= 0:
        return 0.0
    return inter_area / union_area


# =============================================================================
# Label quality helpers
# =============================================================================

_SPECIFIC_TYPES = {
    "door", "window", "stair", "beam", "column", "duct", "pipe",
    "cabin", "meeting_room", "furniture", "equipment",
}


def _is_specific_label(obj: DetectedObjectCreate) -> bool:
    """Return ``True`` if *obj* has a specific, non-generic type label."""
    return obj.object_type in _SPECIFIC_TYPES


# =============================================================================
# Merge strategy
# =============================================================================


def merge_objects(
    rule_objects: List[DetectedObjectCreate],
    ai_objects: List[DetectedObjectCreate],
) -> List[DetectedObjectCreate]:
    """Merge rule-based and AI-detected objects into a single deduplicated list.

    This is a **pure function** — no side effects, no DB I/O.  It only
    reads the two input lists and returns a new list.  This makes it
    straightforward to unit-test.

    Parameters
    ----------
    rule_objects : list[DetectedObjectCreate]
        Objects from CAD/PDF parsers (measured geometry, exact coordinates).
    ai_objects : list[DetectedObjectCreate]
        Objects from the MiMo vision model (may hallucinate, lower precision).

    Returns
    -------
    list[DetectedObjectCreate]
        Merged, deduplicated list with confidence-adjusted scores.
    """
    # ── Edge cases ──────────────────────────────────────────────────────
    if not ai_objects:
        # Keep rule-based objects, but still apply confidence floor
        return [o for o in rule_objects if o.confidence >= CONFIDENCE_FLOOR]

    if not rule_objects:
        # AI-only: all heavily discounted (Case C for everything)
        result: List[DetectedObjectCreate] = []
        for ai_obj in ai_objects:
            obj = _deep_copy(ai_obj)
            obj.confidence = _round4(obj.confidence * 0.6)
            obj.source = "ai"
            if obj.confidence >= CONFIDENCE_FLOOR:
                result.append(obj)
        return _final_dedup(result)

    # ── Main merge loop ─────────────────────────────────────────────────
    merged: List[DetectedObjectCreate] = []
    used_rule_idx: set[int] = set()
    used_ai_idx: set[int] = set()

    for ai_idx, ai_obj in enumerate(ai_objects):
        # Find best IoU match among rule-based objects
        best_iou = 0.0
        best_rule_idx = -1

        for rule_idx, rule_obj in enumerate(rule_objects):
            if not ai_obj.bbox_coords or not rule_obj.bbox_coords:
                continue
            iou = bbox_iou(ai_obj.bbox_coords, rule_obj.bbox_coords)
            if iou > best_iou:
                best_iou = iou
                best_rule_idx = rule_idx

        # ── Case C: No overlap / IoU < 0.2 (AI-only) ────────────────
        if best_iou < IOU_PARTIAL:
            obj = _deep_copy(ai_obj)
            obj.confidence = _round4(obj.confidence * 0.6)
            obj.source = "ai"
            if obj.confidence >= CONFIDENCE_FLOOR:
                merged.append(obj)
                used_ai_idx.add(ai_idx)
            continue

        rule_obj = rule_objects[best_rule_idx]

        # ── Case B: Partial overlap (0.2 <= IoU < 0.4) ──────────────
        if best_iou < IOU_SAME:
            obj = _deep_copy(ai_obj)
            # Borrow rule-based geometry (measured and trusted)
            if rule_obj.bbox_coords:
                obj.bbox_coords = rule_obj.bbox_coords
            if rule_obj.length is not None:
                obj.length = rule_obj.length
            if rule_obj.width is not None:
                obj.width = rule_obj.width
            if rule_obj.area is not None:
                obj.area = rule_obj.area
            # Discounted confidence
            obj.confidence = _round4(ai_obj.confidence * 0.7)
            obj.source = "ai_enhanced"
            if obj.confidence >= CONFIDENCE_FLOOR:
                merged.append(obj)
                used_ai_idx.add(ai_idx)
                used_rule_idx.add(best_rule_idx)
            continue

        # ── Case A: Same object (IoU >= 0.4) ────────────────────────
        # Keep rule-based geometry (measured, not hallucinated)
        obj = _deep_copy(rule_obj)

        # Use AI's label if it's more specific or if rule-based has none
        if (_is_specific_label(ai_obj) and not _is_specific_label(rule_obj)) or (
            ai_obj.label and not rule_obj.label
        ):
            obj.object_type = ai_obj.object_type
            obj.label = ai_obj.label or rule_obj.label

        # Confidence: max of rule-based confidence and discounted AI confidence
        obj.confidence = _round4(max(rule_obj.confidence, ai_obj.confidence * 0.9))
        obj.source = "merged"

        merged.append(obj)
        used_ai_idx.add(ai_idx)
        used_rule_idx.add(best_rule_idx)

    # ── Case D: Rule-based objects with no AI overlap ───────────────────
    for rule_idx, rule_obj in enumerate(rule_objects):
        if rule_idx in used_rule_idx:
            continue
        obj = _deep_copy(rule_obj)
        obj.source = rule_obj.source or "cad"
        merged.append(obj)

    # ── Remove low-confidence objects ────────────────────────────────────
    merged = [o for o in merged if o.confidence >= CONFIDENCE_FLOOR]

    return _final_dedup(merged)


# =============================================================================
# Internal helpers
# =============================================================================


def _deep_copy(obj: DetectedObjectCreate) -> DetectedObjectCreate:
    """Deep-copy a ``DetectedObjectCreate`` (Pydantic v2 compatible)."""
    return obj.model_copy(deep=True)


def _round4(value: float) -> float:
    """Round a float to 4 decimal places for consistent confidence scores."""
    return round(value, 4)


def _final_dedup(objects: List[DetectedObjectCreate]) -> List[DetectedObjectCreate]:
    """Remove near-duplicates from the merged list by bbox IoU.

    Two objects are considered duplicates when they have the same
    ``object_type`` and IoU > ``FINAL_DUP_IOU``.  The object with the
    higher confidence survives.
    """
    if not objects:
        return []

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
            if obj_a.object_type != obj_b.object_type:
                continue
            iou = bbox_iou(bbox_a, bbox_b)
            if iou > FINAL_DUP_IOU:
                if obj_a.confidence >= obj_b.confidence:
                    keep[j] = False
                else:
                    keep[i] = False
                    break

    return [objects[i] for i in range(len(objects)) if keep[i]]
