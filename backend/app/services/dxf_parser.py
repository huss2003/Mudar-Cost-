"""
DXF drawing parser.

Reads DXF files via ezdxf, groups entities by layer convention,
extracts walls, partitions, doors, windows, furniture, and text labels,
and emits a DetectionResult-compatible dict for the Celery pipeline.
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

import ezdxf
from ezdxf.entities import DXFEntity
from ezdxf.math import Vec2

# ---------------------------------------------------------------------------
# Layer → object_type mapping
# ---------------------------------------------------------------------------
LAYER_MAP: Dict[str, str] = {
    "A-WALL": "wall",
    "A-PART": "partition",
    "A-DOOR": "door",
    "A-WINDOW": "window",
    "A-FURN": "furniture",
    "A-TEXT": "other",
    "A-DIMS": "other",
}

# Known block names → object metadata
# (object_type, length_mm, width_mm)
BLOCK_CATALOG: Dict[str, Tuple[str, Optional[float], Optional[float]]] = {
    "DOOR-900": ("door", 900.0, 40.0),
    "DOOR-800": ("door", 800.0, 40.0),
    "DOOR-700": ("door", 700.0, 40.0),
    "WIN-2000": ("window", 2000.0, 1200.0),
    "WIN-1500": ("window", 1500.0, 1200.0),
    "WIN-1200": ("window", 1200.0, 1200.0),
    "WIN-1000": ("window", 1000.0, 1200.0),
    "DESK-1500": ("furniture", 1500.0, 750.0),
    "DESK-1200": ("furniture", 1200.0, 600.0),
    "TABLE-1800": ("furniture", 1800.0, 900.0),
}

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

WALL_THICKNESS_SEARCH_MM = 300.0


def _vec2(point: Any) -> Vec2:
    """Safely convert a point-like object to Vec2."""
    if isinstance(point, Vec2):
        return point
    try:
        x, y = point[0], point[1]
        return Vec2(float(x), float(y))
    except (TypeError, IndexError, ValueError):
        return Vec2(0, 0)


def _line_length(start: Vec2, end: Vec2) -> float:
    return (end - start).magnitude


def _midpoint(start: Vec2, end: Vec2) -> Tuple[float, float]:
    return ((start.x + end.x) / 2.0, (start.y + end.y) / 2.0)


def _bounding_box(points: List[Vec2]) -> List[float]:
    """Return [x1, y1, x2, y2] from a list of Vec2 points."""
    if not points:
        return [0.0, 0.0, 0.0, 0.0]
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _points_close(a: Vec2, b: Vec2, tol: float = 1.0) -> bool:
    """Are two points within tol mm of each other?"""
    return (a - b).magnitude <= tol


def _lines_are_parallel(
    s1: Vec2, e1: Vec2, s2: Vec2, e2: Vec2, tol_deg: float = 5.0
) -> bool:
    """Check if two line segments are approximately parallel."""
    d1 = e1 - s1
    d2 = e2 - s2
    mag1 = d1.magnitude
    mag2 = d2.magnitude
    if mag1 < 1e-6 or mag2 < 1e-6:
        return False
    dot = d1.x * d2.x + d1.y * d2.y
    cos_angle = dot / (mag1 * mag2)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    angle_deg = math.degrees(math.acos(cos_angle))
    return angle_deg <= tol_deg or abs(angle_deg - 180.0) <= tol_deg


def _perpendicular_distance(
    s1: Vec2, e1: Vec2, s2: Vec2, e2: Vec2
) -> float:
    """Compute perpendicular distance between two parallel line segments.

    Uses the distance from midpoint of segment2 to the line of segment1.
    """
    d = e1 - s1
    mag = d.magnitude
    if mag < 1e-6:
        return float("inf")
    # Unit normal to segment 1
    nx = -d.y / mag
    ny = d.x / mag
    mid2 = (s2 + e2) * 0.5
    # Distance from mid2 to line through s1 along normal
    dist = abs((mid2.x - s1.x) * nx + (mid2.y - s1.y) * ny)
    return dist


def _merge_wall_segments(
    lines: List[Tuple[Vec2, Vec2, Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Group connected line segments into continuous wall runs.

    Each input tuple: (start, end, attributes_dict).
    Returns a list of merged wall dicts with merged points list.
    """
    if not lines:
        return []

    # Build adjacency: for each endpoint, find all segments sharing it
    # Track which segments have been consumed
    segments = [(s, e, attr) for s, e, attr in lines]
    used = [False] * len(segments)
    merged: List[Dict[str, Any]] = []

    for i in range(len(segments)):
        if used[i]:
            continue
        # Start a new group
        group = [segments[i]]
        used[i] = True
        changed = True
        while changed:
            changed = False
            for j in range(len(segments)):
                if used[j]:
                    continue
                s_j, e_j, _ = segments[j]
                # Check if this segment connects to any endpoint in the group
                for k, (s_k, e_k, _) in enumerate(group):
                    if _points_close(s_j, e_k) or _points_close(e_j, e_k) or \
                       _points_close(s_j, s_k) or _points_close(e_j, s_k):
                        group.append(segments[j])
                        used[j] = True
                        changed = True
                        break
        # Collect all unique points from the group
        all_points: List[Vec2] = []
        for s, e, _ in group:
            all_points.append(s)
            all_points.append(e)
        # Build an ordered polyline from the connected segments
        ordered = _order_connected_segments(group)

        merged.append({
            "points": ordered,
            "segments": group,
            "entity_count": len(group),
            "total_length": sum(
                _line_length(s, e) for s, e, _ in group
            ),
            "bbox": _bounding_box(all_points),
        })

    return merged


def _order_connected_segments(
    segments: List[Tuple[Vec2, Vec2, Any]],
) -> List[Vec2]:
    """Order connected segments into a continuous polyline (march)."""
    if not segments:
        return []
    if len(segments) == 1:
        s, e, _ = segments[0]
        return [s, e]

    # Make a mutable copy: (start, end, idx)
    segs = [(s, e, i) for i, (s, e, _) in enumerate(segments)]
    ordered: List[Vec2] = []
    current = segs.pop(0)
    ordered.append(current[0])
    ordered.append(current[1])
    current_end = current[1]

    while segs:
        found = False
        for idx, (s, e, _) in enumerate(segs):
            if _points_close(s, current_end):
                ordered.append(e)
                current_end = e
                segs.pop(idx)
                found = True
                break
            elif _points_close(e, current_end):
                ordered.append(s)
                current_end = s
                segs.pop(idx)
                found = True
                break
        if not found:
            # Gap — start a new chain from remaining
            if segs:
                s, e, _ = segs.pop(0)
                ordered.append(s)
                ordered.append(e)
                current_end = e
    return ordered


def _detect_wall_thickness(
    entity_start: Vec2,
    entity_end: Vec2,
    all_lines_on_layer: List[Tuple[Vec2, Vec2]],
    max_search: float = WALL_THICKNESS_SEARCH_MM,
) -> Optional[float]:
    """Try to find a parallel line nearby to determine wall thickness."""
    for s2, e2 in all_lines_on_layer:
        if not _lines_are_parallel(entity_start, entity_end, s2, e2):
            continue
        dist = _perpendicular_distance(
            entity_start, entity_end, s2, e2
        )
        if 0.5 < dist <= max_search:
            return round(dist, 1)
    return None


# ---------------------------------------------------------------------------
# Entity extraction helpers
# ---------------------------------------------------------------------------


def _extract_line(
    entity: DXFEntity,
) -> Optional[Tuple[Vec2, Vec2, Dict[str, Any]]]:
    """Extract start/end from a LINE entity.

    Returns (start, end, attributes) or None.
    """
    try:
        start = _vec2(entity.dxf.start)
        end = _vec2(entity.dxf.end)
        if (end - start).magnitude < 1.0:
            return None  # skip zero-length lines
        return (start, end, {"line_type": "LINE"})
    except AttributeError:
        return None


def _extract_lwpolyline_vertices(
    entity: DXFEntity,
) -> Optional[List[Vec2]]:
    """Get vertices from an LWPOLYLINE as a list of Vec2."""
    try:
        points = list(entity.get_points("xy"))
        if len(points) < 2:
            return None
        # LWPOLYLINE is closed if flags & 1
        return [Vec2(x, y) for x, y in points]
    except (AttributeError, ValueError):
        return None


def _lwpolyline_to_segments(
    vertices: List[Vec2],
) -> List[Tuple[Vec2, Vec2, Dict[str, Any]]]:
    """Break a closed LWPOLYLINE into individual edge segments."""
    segments: List[Tuple[Vec2, Vec2, Dict[str, Any]]] = []
    for i in range(len(vertices) - 1):
        s = vertices[i]
        e = vertices[i + 1]
        length = (e - s).magnitude
        if length >= 1.0:
            segments.append((s, e, {"line_type": "LWPOLYLINE_EDGE"}))
    # Close the loop if start != end
    if len(vertices) > 2 and (vertices[-1] - vertices[0]).magnitude >= 1.0:
        segments.append(
            (vertices[-1], vertices[0], {"line_type": "LWPOLYLINE_EDGE"})
        )
    return segments


def _extract_blockref(
    entity: DXFEntity,
) -> Optional[Dict[str, Any]]:
    """Extract block reference information.

    Returns a dict with block name, insertion point, and catalog data.
    """
    try:
        block_name = entity.dxf.name.upper()
    except AttributeError:
        return None

    try:
        insert = _vec2(entity.dxf.insert)
    except AttributeError:
        insert = Vec2(0, 0)

    return {
        "block_name": block_name,
        "insert": insert,
    }


def _extract_text(
    entity: DXFEntity,
) -> Optional[Dict[str, Any]]:
    """Extract text content and position from TEXT or MTEXT."""
    try:
        if entity.dxftype() == "MTEXT":
            text = entity.text  # property, not dxf
        else:
            text = entity.dxf.text
    except AttributeError:
        return None

    # Try insert first, then alignment_point
    try:
        pos = _vec2(entity.dxf.insert)
    except AttributeError:
        try:
            pos = _vec2(entity.dxf.alignment_point)
        except AttributeError:
            pos = Vec2(0, 0)

    return {
        "text": text.strip() if text else "",
        "position": pos,
    }


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------


def parse_dxf(
    filepath: str,
    drawing_id: int = 0,
) -> Dict[str, Any]:
    """Parse a DXF file and return a DetectionResult-compatible dict.

    Args:
        filepath: Absolute path to the .dxf file.
        drawing_id: Database ID of the drawing record.

    Returns:
        Dict with keys matching ``app.schemas.detection.DetectionResult``:
            - drawing_id
            - status
            - objects: list of DetectedObjectCreate-like dicts
            - errors: list of warning/error strings
            - processing_time_ms
            - source_format

    Raises:
        FileNotFoundError: If *filepath* does not exist.
        ezdxf.DXFStructureError: If the file is corrupt or not a DXF.
    """
    start_ts = time.perf_counter()
    errors: List[str] = []
    objects: List[Dict[str, Any]] = []
    source_format: str = "dxf"

    # ------------------------------------------------------------------
    # 1. Load the DXF document
    # ------------------------------------------------------------------
    doc = ezdxf.readfile(filepath)

    if doc is None:
        errors.append("ezdxf returned None when reading file")
        return _result(drawing_id, objects, errors, start_ts, source_format)

    msp = doc.modelspace()

    # ------------------------------------------------------------------
    # 2. Collect entities grouped by layer
    # ------------------------------------------------------------------
    layer_entities: Dict[str, List[DXFEntity]] = {}
    for entity in msp:
        try:
            layer = entity.dxf.layer
        except AttributeError:
            layer = "0"
        layer_entities.setdefault(layer, []).append(entity)

    if not layer_entities:
        errors.append("No entities found in modelspace")
        return _result(drawing_id, objects, errors, start_ts, source_format)

    # ------------------------------------------------------------------
    # 3. Process each layer
    # ------------------------------------------------------------------
    for layer_name, entities in layer_entities.items():
        object_type = LAYER_MAP.get(layer_name, "other")

        # Collect all LINE endpoints on this layer for thickness detection
        raw_lines: List[Tuple[Vec2, Vec2, Dict[str, Any]]] = []
        raw_line_endpoints: List[Tuple[Vec2, Vec2]] = []

        for entity in entities:
            dxftype = entity.dxftype()

            try:
                if dxftype == "LINE":
                    result = _extract_line(entity)
                    if result:
                        s, e, attr = result
                        raw_lines.append(result)
                        raw_line_endpoints.append((s, e))

                elif dxftype == "LWPOLYLINE":
                    verts = _extract_lwpolyline_vertices(entity)
                    if verts:
                        segs = _lwpolyline_to_segments(verts)
                        for s, e, attr in segs:
                            raw_lines.append((s, e, attr))
                            raw_line_endpoints.append((s, e))

                elif dxftype == "INSERT":
                    _process_blockref(
                        entity, layer_name, object_type, objects, errors
                    )

                elif dxftype in ("TEXT", "MTEXT"):
                    _process_text(
                        entity, layer_name, objects
                    )

                elif dxftype == "DIMENSION":
                    # Dimensions are annotations — skip or store as meta
                    pass

                else:
                    pass  # skip unhandled types

            except Exception as exc:
                errors.append(
                    f"Error processing {dxftype} on layer {layer_name}: {exc}"
                )

        # Process collected lines for wall/partition layers
        if object_type in ("wall", "partition") and raw_lines:
            _process_wall_lines(
                raw_lines,
                raw_line_endpoints,
                layer_name,
                object_type,
                objects,
            )
        elif object_type == "other" and raw_lines:
            # Non-wall lines — treat as generic linear objects
            for s, e, attr in raw_lines:
                length = _line_length(s, e)
                mx, my = _midpoint(s, e)
                bbox = _bounding_box([s, e])
                objects.append(
                    _make_detected_object(
                        object_type="other",
                        layer=layer_name,
                        length=length,
                        location_x=mx,
                        location_y=my,
                        bbox_coords=bbox,
                        raw_attributes={
                            "entity_count": 1,
                            "line_type": attr.get("line_type", "LINE"),
                        },
                    )
                )

    return _result(drawing_id, objects, errors, start_ts, source_format)


# ---------------------------------------------------------------------------
# Layer-specific processors
# ---------------------------------------------------------------------------


def _process_wall_lines(
    raw_lines: List[Tuple[Vec2, Vec2, Dict[str, Any]]],
    raw_line_endpoints: List[Tuple[Vec2, Vec2]],
    layer_name: str,
    object_type: str,
    objects: List[Dict[str, Any]],
) -> None:
    """Process LINE/LWPOLYLINE entities on wall/partition layers.

    Merges connected segments and attempts wall thickness detection.
    """
    if not raw_lines:
        return

    # Merge connected segments into continuous wall runs
    merged_segments = _merge_wall_segments(raw_lines)

    for wall in merged_segments:
        points: List[Vec2] = wall["points"]
        if len(points) < 2:
            continue

        total_length = wall["total_length"]
        bbox = wall["bbox"]

        # Midpoint of the wall run
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = (bbox[1] + bbox[3]) / 2.0

        # Try to detect wall thickness from the first segment
        thickness: Optional[float] = None
        if raw_line_endpoints:
            s = points[0]
            e = points[1] if len(points) > 1 else points[0]
            thickness = _detect_wall_thickness(s, e, raw_line_endpoints)

        objects.append(
            _make_detected_object(
                object_type=object_type,
                layer=layer_name,
                length=round(total_length, 1),
                thickness=thickness,
                width=thickness,
                location_x=round(cx, 1),
                location_y=round(cy, 1),
                bbox_coords=[round(v, 1) for v in bbox],
                polyline_json=[
                    {"x": round(p.x, 1), "y": round(p.y, 1)}
                    for p in points
                ],
                raw_attributes={
                    "entity_count": wall["entity_count"],
                    "line_type": "MERGED_WALL",
                },
            )
        )


def _process_blockref(
    entity: DXFEntity,
    layer_name: str,
    object_type: str,
    objects: List[Dict[str, Any]],
    errors: List[str],
) -> None:
    """Process an INSERT (block reference) entity."""
    info = _extract_blockref(entity)
    if info is None:
        return

    block_name = info["block_name"]
    insert_pt = info["insert"]

    # Look up in catalog
    catalog_entry = BLOCK_CATALOG.get(block_name)

    if catalog_entry is None:
        errors.append(
            f"Skipping unknown block '{block_name}' on layer '{layer_name}'"
        )
        return

    cat_type, cat_length, cat_width = catalog_entry

    # Compute bounding box from insertion point + block size
    if cat_length is not None and cat_width is not None:
        half_l = cat_length / 2.0
        half_w = cat_width / 2.0
        bbox = [
            insert_pt.x - half_l,
            insert_pt.y - half_w,
            insert_pt.x + half_l,
            insert_pt.y + half_w,
        ]
    else:
        bbox = [insert_pt.x, insert_pt.y, insert_pt.x, insert_pt.y]

    # Rotation
    try:
        rotation = float(entity.dxf.rotation)
    except (AttributeError, ValueError):
        rotation = 0.0

    objects.append(
        _make_detected_object(
            object_type=cat_type,
            label=None,
            layer=layer_name,
            length=cat_length,
            width=cat_width,
            height=None,
            thickness=cat_width if cat_type in ("door", "window") else None,
            location_x=round(insert_pt.x, 1),
            location_y=round(insert_pt.y, 1),
            rotation=rotation,
            bbox_coords=[round(v, 1) for v in bbox],
            raw_attributes={
                "block_name": block_name,
                "entity_count": 1,
            },
        )
    )


def _process_text(
    entity: DXFEntity,
    layer_name: str,
    objects: List[Dict[str, Any]],
) -> None:
    """Process a TEXT or MTEXT entity."""
    info = _extract_text(entity)
    if info is None:
        return

    text = info.get("text", "")
    if not text:
        return

    pos = info["position"]

    objects.append(
        _make_detected_object(
            object_type="other",
            label=text,
            layer=layer_name,
            location_x=round(pos.x, 1),
            location_y=round(pos.y, 1),
            confidence=1.0,
            source="cad",
            bbox_coords=[round(pos.x, 1), round(pos.y, 1),
                         round(pos.x, 1), round(pos.y, 1)],
            raw_attributes={"label": text},
        )
    )


# ---------------------------------------------------------------------------
# Dict building
# ---------------------------------------------------------------------------


def _make_detected_object(
    object_type: str,
    layer: Optional[str] = None,
    label: Optional[str] = None,
    length: Optional[float] = None,
    width: Optional[float] = None,
    area: Optional[float] = None,
    height: Optional[float] = None,
    thickness: Optional[float] = None,
    location_x: Optional[float] = None,
    location_y: Optional[float] = None,
    rotation: Optional[float] = None,
    raw_attributes: Optional[Dict[str, Any]] = None,
    bbox_coords: Optional[List[float]] = None,
    polyline_json: Optional[List[Dict[str, Any]]] = None,
    confidence: float = 1.0,
    source: str = "cad",
) -> Dict[str, Any]:
    """Build a DetectedObjectCreate-compatible dict, omitting None values."""
    obj: Dict[str, Any] = {
        "object_type": object_type,
        "label": label,
        "confidence": confidence,
        "source": source,
    }
    if layer is not None:
        obj["layer"] = layer
    if length is not None:
        obj["length"] = length
    if width is not None:
        obj["width"] = width
    if area is not None:
        obj["area"] = area
    if height is not None:
        obj["height"] = height
    if thickness is not None:
        obj["thickness"] = thickness
    if location_x is not None:
        obj["location_x"] = location_x
    if location_y is not None:
        obj["location_y"] = location_y
    if rotation is not None:
        obj["rotation"] = rotation
    if raw_attributes:
        obj["raw_attributes"] = raw_attributes
    if bbox_coords is not None:
        obj["bbox_coords"] = bbox_coords
    if polyline_json is not None:
        obj["polyline_json"] = polyline_json
    return obj


def _result(
    drawing_id: int,
    objects: List[Dict[str, Any]],
    errors: List[str],
    start_ts: float,
    source_format: str,
) -> Dict[str, Any]:
    """Build the final DetectionResult-compatible dict."""
    elapsed_ms = round((time.perf_counter() - start_ts) * 1000, 1)
    status = "completed" if not errors else "completed_with_errors"
    return {
        "drawing_id": drawing_id,
        "status": status,
        "objects": objects,
        "errors": errors,
        "processing_time_ms": elapsed_ms,
        "source_format": source_format,
    }


def points_to_vec2(points: List[Any]) -> List[Vec2]:
    """Convert a list of point-like objects to Vec2."""
    return [_vec2(p) for p in points]
