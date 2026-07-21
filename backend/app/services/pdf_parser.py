"""PDF drawing parser — layered extraction from vector, text, OpenCV, and tables.

Uses a 4-layer fallback strategy:

    Layer 1 — PyMuPDF (fitz) vector graphics extraction
    Layer 2 — PyMuPDF text extraction (labels, dimensions)
    Layer 3 — OpenCV Hough Line Transform (scanned / raster PDF fallback)
    Layer 4 — pdfplumber table extraction (material schedules, BOQ tables)

Each layer is wrapped in try/except so later layers still run if one fails.
Output is normalised to the same DetectedObjectCreate / DetectionResult
schema used by the CAD parser.
"""

from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.schemas.detection import DetectedObjectCreate, DetectionResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PDF_POINT_TO_MM: float = 0.3528  # 1 PostScript point = 1/72 inch = 0.3528 mm
MM_PER_INCH: float = 25.4

# Classification thresholds operate on paper-space mm values.
# A typical floor-plan PDF at 1:100 scale renders a 10 m wall as
# ~100 mm on paper — all thresholds here are in paper-space mm.

# Minimum rect area (mm²) to be considered a structural element
MIN_WALL_AREA_MM2: float = 2000.0   # large room outline / building footprint
MIN_PARTITION_AREA_MM2: float = 200.0
MAX_DOOR_AREA_MM2: float = 2000.0
MAX_WINDOW_AREA_MM2: float = 2000.0

# Line length thresholds (in PDF points)
LINE_WALL_MIN_PT: float = 80.0     # ~28 mm — long lines are walls
LINE_PARTITION_MIN_PT: float = 20.0  # ~7 mm — shorter lines

# Line length thresholds for Hough (in pixels, before scale calibration)
HOUGH_MIN_LINE_LENGTH: int = 30
HOUGH_MAX_LINE_GAP: int = 10
CANNY_THRESHOLD_1: int = 50
CANNY_THRESHOLD_2: int = 150

# Aspect ratio thresholds for classification
DOOR_ASPECT_MIN: float = 2.0   # door indicators are wide & thin
WINDOW_ASPECT_MIN: float = 2.5  # window indicators are thin rectangles


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pt_to_mm(value: float) -> float:
    """Convert PDF points to millimetres."""
    return value * PDF_POINT_TO_MM


def _rect_center(rect: Tuple[float, float, float, float]) -> Tuple[float, float]:
    """Return (cx, cy) for a bbox (x0, y0, x1, y1)."""
    return ((rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0)


def _rect_area(rect: Tuple[float, float, float, float]) -> float:
    """Return area of a bbox (x0, y0, x1, y1) in points²."""
    return (rect[2] - rect[0]) * (rect[3] - rect[1])


def _rect_width(rect: Tuple[float, float, float, float]) -> float:
    return rect[2] - rect[0]


def _rect_height(rect: Tuple[float, float, float, float]) -> float:
    return rect[3] - rect[1]


def _rect_to_mm(rect: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    """Convert a bbox from PDF points to mm."""
    return tuple(_pt_to_mm(v) for v in rect)


def _classify_rect(
    rect_mm: Tuple[float, float, float, float],
) -> str:
    """Heuristic classification of a rectangle into an object type.

    Uses area and aspect ratio rules tuned for floor-plan PDFs.
    All values are in paper-space mm.
    """
    w = _rect_width(rect_mm)
    h = _rect_height(rect_mm)
    area = w * h
    if min(w, h) > 0:
        aspect = max(w, h) / min(w, h)
    else:
        aspect = 1.0

    # Large rectangle → building footprint / room outline → wall
    if area >= MIN_WALL_AREA_MM2:
        return "wall"

    # Medium rectangle → inner partition or feature
    if area >= MIN_PARTITION_AREA_MM2:
        if aspect >= WINDOW_ASPECT_MIN and area < MAX_WINDOW_AREA_MM2:
            return "window"
        return "partition"

    # Small rectangle — check aspect for door / window
    # Doors are wide (width >= height), windows are tall (height > width)
    if aspect >= DOOR_ASPECT_MIN and area < MAX_DOOR_AREA_MM2:
        if w >= h:
            return "door"
        else:
            return "window"
    if aspect >= WINDOW_ASPECT_MIN and area < MAX_WINDOW_AREA_MM2:
        if w >= h:
            return "door"
        else:
            return "window"

    return "furniture" if area > 50.0 else "other"


def _line_length(x1: float, y1: float, x2: float, y2: float) -> float:
    """Euclidean distance between two points."""
    return math.hypot(x2 - x1, y2 - y1)


# ---------------------------------------------------------------------------
# Layer 1: PyMuPDF (fitz) vector extraction
# ---------------------------------------------------------------------------

def _layer_pymupdf_vectors(filepath: str) -> List[DetectedObjectCreate]:
    """Extract vector graphics (lines, rects, curves) via fitz.

    Returns a list of DetectedObjectCreate with confidence=0.9 for
    vector-sourced objects.
    """
    import fitz

    objects: List[DetectedObjectCreate] = []
    doc = fitz.open(filepath)

    try:
        for page_num, page in enumerate(doc):
            paths = page.get_drawings()
            logger.debug("Page %d: %d drawing paths", page_num, len(paths))

            for path in paths:
                raw = {
                    "page": page_num,
                    "color": getattr(path.get("color"), "hex", None),
                    "width": path.get("width"),
                    "fill": getattr(path.get("fill"), "hex", None),
                    "path_type": path.get("type"),
                }
                rect = path.get("rect")
                if rect is None:
                    continue

                # Convert rect to mm
                rect_mm = _rect_to_mm(tuple(rect))  # type: ignore[arg-type]
                cx, cy = _rect_center(rect_mm)
                w_mm = _rect_width(rect_mm)
                h_mm = _rect_height(rect_mm)
                area_mm2 = w_mm * h_mm

                items = path.get("items", [])

                # --- LINE items ---
                line_objects = _extract_lines(items, page_num)
                objects.extend(line_objects)

                # --- RECT items ---
                rect_objects = _extract_rects(items, rect_mm, cx, cy, w_mm, h_mm, area_mm2, raw)
                objects.extend(rect_objects)

    finally:
        doc.close()

    return objects


def _extract_lines(
    items: List[tuple], page_num: int
) -> List[DetectedObjectCreate]:
    """Extract line segments from drawing items and convert to wall-like objects.

    fitz line items have the structure: ('l', Point(x1,y1), Point(x2,y2))
    where each Point has .x and .y attributes.
    """
    objects: List[DetectedObjectCreate] = []
    for item in items:
        kind = item[0]
        if kind != "l":  # 'l' = line
            continue
        # fitz line items: ('l', Point(x1,y1), Point(x2,y2))
        if len(item) < 3:
            continue
        _, p1, p2 = item[:3]
        x1 = p1.x if hasattr(p1, 'x') else p1[0]
        y1 = p1.y if hasattr(p1, 'y') else p1[1]
        x2 = p2.x if hasattr(p2, 'x') else p2[0]
        y2 = p2.y if hasattr(p2, 'y') else p2[1]
        length_pt = _line_length(x1, y1, x2, y2)
        length_mm = _pt_to_mm(length_pt)
        cx_pt = (x1 + x2) / 2.0
        cy_pt = (y1 + y2) / 2.0

        # Determine if this looks like a wall vs partition vs other
        # Walls are long lines (>~80 pts ≈ ~28 mm on paper)
        obj_type = "wall" if length_pt >= LINE_WALL_MIN_PT else "partition"

        objects.append(
            DetectedObjectCreate(
                object_type=obj_type,
                label=None,
                length=round(length_mm, 2),
                width=round(_pt_to_mm(1.0), 2),  # default line width
                area=None,
                height=None,
                thickness=None,
                location_x=round(_pt_to_mm(cx_pt), 2),
                location_y=round(_pt_to_mm(cy_pt), 2),
                layer="vector_line",
                rotation=None,
                raw_attributes={
                    "source_layer": "pymupdf_vector",
                    "page": page_num,
                    "x1_pt": round(x1, 2),
                    "y1_pt": round(y1, 2),
                    "x2_pt": round(x2, 2),
                    "y2_pt": round(y2, 2),
                },
                bbox_coords=[
                    round(_pt_to_mm(min(x1, x2)), 2),
                    round(_pt_to_mm(min(y1, y2)), 2),
                    round(_pt_to_mm(max(x1, x2)), 2),
                    round(_pt_to_mm(max(y1, y2)), 2),
                ],
                polyline_json=[
                    {"x": round(_pt_to_mm(x1), 2), "y": round(_pt_to_mm(y1), 2)},
                    {"x": round(_pt_to_mm(x2), 2), "y": round(_pt_to_mm(y2), 2)},
                ],
                confidence=0.9,
                source="pdf",
            )
        )
    return objects


def _extract_rects(
    items: List[tuple],
    rect_mm: Tuple[float, float, float, float],
    cx: float,
    cy: float,
    w_mm: float,
    h_mm: float,
    area_mm2: float,
    raw: dict,
) -> List[DetectedObjectCreate]:
    """Extract rectangle items from drawing path items.

    fitz rect items have the structure: ('re', Rect(x0,y0,x1,y1), seq_no)
    where Rect has .x0, .y0, .x1, .y1, .width, .height attributes.
    """
    objects: List[DetectedObjectCreate] = []
    for item in items:
        kind = item[0]
        if kind != "re":  # 're' = rectangle
            continue
        # fitz rect items: ('re', Rect(x0,y0,x1,y1), seq_no)
        if len(item) < 2:
            continue
        r = item[1]
        # Handle both Rect objects and raw tuples
        if hasattr(r, 'x0'):
            rx = r.x0
            ry = r.y0
            rw = r.width
            rh = r.height
        else:
            rx, ry, rw, rh = r[0], r[1], r[2] - r[0], r[3] - r[1]

        obj_type = _classify_rect(rect_mm)
        obj = DetectedObjectCreate(
            object_type=obj_type,
            label=None,
            length=round(w_mm, 2),
            width=round(h_mm, 2),
            area=round(area_mm2, 2),
            area_unit="sqmm",
            height=None,
            thickness=None,
            location_x=round(cx, 2),
            location_y=round(cy, 2),
            layer="vector_rect",
            rotation=None,
            raw_attributes={
                **raw,
                "source_layer": "pymupdf_vector",
                "rect_x_pt": round(rx, 2),
                "rect_y_pt": round(ry, 2),
                "rect_w_pt": round(rw, 2),
                "rect_h_pt": round(rh, 2),
            },
            bbox_coords=list(round(v, 2) for v in rect_mm),
            polyline_json=[
                {"x": round(rect_mm[0], 2), "y": round(rect_mm[1], 2)},
                {"x": round(rect_mm[2], 2), "y": round(rect_mm[3], 2)},
            ],
            confidence=0.9,
            source="pdf",
        )
        objects.append(obj)
    return objects


# ---------------------------------------------------------------------------
# Layer 2: PyMuPDF text extraction
# ---------------------------------------------------------------------------

def _layer_pymupdf_text(filepath: str) -> List[DetectedObjectCreate]:
    """Extract text labels and dimensions from the PDF.

    Returns objects of type 'other' with the extracted text stored in
    the label field and raw_attributes containing position info.
    """
    import fitz

    objects: List[DetectedObjectCreate] = []
    doc = fitz.open(filepath)

    try:
        for page_num, page in enumerate(doc):
            # --- Block-level text ---
            blocks = page.get_text("blocks")
            for block in blocks:
                # block = (x0, y0, x1, y1, "text", block_no, block_type)
                if len(block) < 5:
                    continue
                x0, y0, x1, y1 = block[:4]
                text = (block[4] or "").strip()
                if not text:
                    continue
                bbox_mm = _rect_to_mm((x0, y0, x1, y1))
                cx, cy = _rect_center(bbox_mm)
                objects.append(
                    DetectedObjectCreate(
                        object_type="other",
                        label=text,
                        location_x=round(cx, 2),
                        location_y=round(cy, 2),
                        layer="text_block",
                        raw_attributes={
                            "source_layer": "pymupdf_text",
                            "page": page_num,
                            "text_type": "block",
                        },
                        bbox_coords=list(round(v, 2) for v in bbox_mm),
                        confidence=0.7,
                        source="pdf",
                    )
                )

            # --- Word-level text ---
            words = page.get_text("words")
            for word in words:
                # word = (x0, y0, x1, y1, "word", block_no, line_no, word_no)
                if len(word) < 5:
                    continue
                x0, y0, x1, y1 = word[:4]
                text = (word[4] or "").strip()
                if not text:
                    continue
                bbox_mm = _rect_to_mm((x0, y0, x1, y1))
                cx, cy = _rect_center(bbox_mm)
                objects.append(
                    DetectedObjectCreate(
                        object_type="other",
                        label=text,
                        location_x=round(cx, 2),
                        location_y=round(cy, 2),
                        layer="text_word",
                        raw_attributes={
                            "source_layer": "pymupdf_text",
                            "page": page_num,
                            "text_type": "word",
                        },
                        bbox_coords=list(round(v, 2) for v in bbox_mm),
                        confidence=0.6,
                        source="pdf",
                    )
                )
    finally:
        doc.close()

    return objects


# ---------------------------------------------------------------------------
# Layer 3: OpenCV Hough Line Transform
# ---------------------------------------------------------------------------

def _layer_opencv_hough(filepath: str) -> List[DetectedObjectCreate]:
    """Convert PDF page to image and run Probabilistic Hough Line Transform.

    Uses page pixmap → numpy array → grayscale → Canny → HoughLinesP.
    This is a fallback for scanned / raster-heavy PDFs where vector
    extraction returns little or nothing.
    """
    import cv2
    import fitz

    objects: List[DetectedObjectCreate] = []
    doc = fitz.open(filepath)

    try:
        for page_num, page in enumerate(doc):
            # Render page at 200 DPI for a decent pixel grid
            zoom = 200.0 / 72.0  # 72 DPI is default PDF resolution
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            # Pixmap → numpy array (RGB)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            if pix.n >= 3:
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            else:
                gray = img

            # Edge detection
            edges = cv2.Canny(gray, CANNY_THRESHOLD_1, CANNY_THRESHOLD_2)

            # Probabilistic Hough Line Transform
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=math.pi / 180.0,
                threshold=50,
                minLineLength=HOUGH_MIN_LINE_LENGTH,
                maxLineGap=HOUGH_MAX_LINE_GAP,
            )

            if lines is None:
                continue

            # OpenCV versions differ on output shape:
            #   older: (N, 1, 4)   newer: (N, 4)
            lines = lines.reshape(-1, 4)

            for line in lines:
                x1, y1, x2, y2 = line
                length_px = _line_length(x1, y1, x2, y2)
                if length_px < HOUGH_MIN_LINE_LENGTH:
                    continue

                # Angle in degrees (0 = horizontal)
                angle = math.degrees(math.atan2(y2 - y1, x2 - x1))

                # Convert pixel coords back to PDF points, then to mm
                # Pixel = point * zoom, so point = pixel / zoom
                x1_pt = x1 / zoom
                y1_pt = y1 / zoom
                x2_pt = x2 / zoom
                y2_pt = y2 / zoom
                length_pt = _line_length(x1_pt, y1_pt, x2_pt, y2_pt)
                length_mm = _pt_to_mm(length_pt)
                cx_pt = (x1_pt + x2_pt) / 2.0
                cy_pt = (y1_pt + y2_pt) / 2.0

                # Classify by length (paper-space mm threshold)
                obj_type = "wall" if length_pt >= LINE_WALL_MIN_PT else "partition"

                objects.append(
                    DetectedObjectCreate(
                        object_type=obj_type,
                        label=None,
                        length=round(length_mm, 2),
                        width=None,
                        area=None,
                        height=None,
                        thickness=None,
                        location_x=round(_pt_to_mm(cx_pt), 2),
                        location_y=round(_pt_to_mm(cy_pt), 2),
                        layer="hough_line",
                        rotation=round(angle, 1),
                        raw_attributes={
                            "source_layer": "opencv_hough",
                            "page": page_num,
                            "x1_px": int(x1),
                            "y1_px": int(y1),
                            "x2_px": int(x2),
                            "y2_px": int(y2),
                            "length_px": round(length_px, 1),
                            "dpi": 200,
                        },
                        bbox_coords=[
                            round(_pt_to_mm(min(x1_pt, x2_pt)), 2),
                            round(_pt_to_mm(min(y1_pt, y2_pt)), 2),
                            round(_pt_to_mm(max(x1_pt, x2_pt)), 2),
                            round(_pt_to_mm(max(y1_pt, y2_pt)), 2),
                        ],
                        polyline_json=[
                            {"x": round(_pt_to_mm(x1_pt), 2), "y": round(_pt_to_mm(y1_pt), 2)},
                            {"x": round(_pt_to_mm(x2_pt), 2), "y": round(_pt_to_mm(y2_pt), 2)},
                        ],
                        confidence=0.5,  # lower confidence — image-based
                        source="pdf",
                    )
                )
    finally:
        doc.close()

    return objects


# ---------------------------------------------------------------------------
# Layer 4: pdfplumber table extraction
# ---------------------------------------------------------------------------

def _layer_pdfplumber_tables(filepath: str) -> List[DetectedObjectCreate]:
    """Extract tables from the PDF via pdfplumber.

    Useful for material schedules, BOQ tables, and dimension tables
    embedded in drawing PDFs. Each table row becomes an 'other' object
    with structured data in raw_attributes.
    """
    import pdfplumber

    objects: List[DetectedObjectCreate] = []

    with pdfplumber.open(filepath) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            if not tables:
                continue

            for table_idx, table in enumerate(tables):
                if not table or not table[0]:
                    continue

                header = [str(c).strip() if c else "" for c in table[0]]
                for row_idx, row in enumerate(table[1:], start=1):
                    if not row or all(c is None or str(c).strip() == "" for c in row):
                        continue

                    row_data: Dict[str, Any] = {}
                    for col_idx, cell in enumerate(row):
                        col_name = header[col_idx] if col_idx < len(header) else f"col_{col_idx}"
                        row_data[col_name] = str(cell).strip() if cell else ""

                    objects.append(
                        DetectedObjectCreate(
                            object_type="other",
                            label=row_data.get(header[0] if header else "item", str(row_idx)),
                            layer=f"table_{table_idx}",
                            raw_attributes={
                                "source_layer": "pdfplumber_table",
                                "page": page_num,
                                "table_index": table_idx,
                                "row_index": row_idx,
                                "header": header,
                                "row_data": row_data,
                            },
                            confidence=0.6,
                            source="pdf",
                        )
                    )
    return objects


# ---------------------------------------------------------------------------
# Main parser entry point
# ---------------------------------------------------------------------------

def parse_pdf(filepath: str, drawing_id: int = 0) -> DetectionResult:
    """Parse a PDF drawing file using a 4-layer approach.

    Each layer is wrapped in try/except so a failure in one does not
    prevent later (fallback) layers from running.

    Args:
        filepath: Absolute path to the PDF file on disk.
        drawing_id: Database drawing ID to attach to the result.

    Returns:
        A DetectionResult containing all detected objects across layers.
    """
    start = time.perf_counter()
    all_objects: Dict[str, DetectedObjectCreate] = {}  # dedup by (page, type, location)
    errors: List[str] = []
    layer_had_data = False

    # ── Layer 1: PyMuPDF vector extraction ────────────────────────────
    try:
        vec_objects = _layer_pymupdf_vectors(filepath)
        if vec_objects:
            layer_had_data = True
            logger.info("Layer 1 (PyMuPDF vectors): %d objects", len(vec_objects))
            for obj in vec_objects:
                _dedup_add(all_objects, obj)
        else:
            logger.info("Layer 1 (PyMuPDF vectors): no objects found")
    except Exception as exc:
        msg = f"Layer 1 (PyMuPDF vectors) failed: {exc}"
        logger.warning(msg)
        errors.append(msg)

    # ── Layer 2: PyMuPDF text extraction ──────────────────────────────
    try:
        text_objects = _layer_pymupdf_text(filepath)
        if text_objects:
            logger.info("Layer 2 (PyMuPDF text): %d objects", len(text_objects))
            for obj in text_objects:
                _dedup_add(all_objects, obj)
    except Exception as exc:
        msg = f"Layer 2 (PyMuPDF text) failed: {exc}"
        logger.warning(msg)
        errors.append(msg)

    # ── Layer 3: OpenCV Hough Line Transform ──────────────────────────
    # Only run if vector layer returned little or nothing (scanned PDF)
    if not layer_had_data:
        try:
            hough_objects = _layer_opencv_hough(filepath)
            if hough_objects:
                logger.info("Layer 3 (OpenCV Hough): %d objects", len(hough_objects))
                for obj in hough_objects:
                    _dedup_add(all_objects, obj)
        except Exception as exc:
            msg = f"Layer 3 (OpenCV Hough) failed: {exc}"
            logger.warning(msg)
            errors.append(msg)
    else:
        logger.info("Layer 3 (OpenCV Hough): skipped — vector data present")

    # ── Layer 4: pdfplumber table extraction ──────────────────────────
    try:
        table_objects = _layer_pdfplumber_tables(filepath)
        if table_objects:
            logger.info("Layer 4 (pdfplumber tables): %d objects", len(table_objects))
            for obj in table_objects:
                _dedup_add(all_objects, obj)
    except Exception as exc:
        msg = f"Layer 4 (pdfplumber tables) failed: {exc}"
        logger.warning(msg)
        errors.append(msg)

    elapsed = (time.perf_counter() - start) * 1000.0  # ms

    result = DetectionResult(
        drawing_id=drawing_id,
        status="completed" if not errors else "completed_with_errors",
        objects=list(all_objects.values()),
        errors=errors,
        processing_time_ms=round(elapsed, 2),
        source_format="pdf",
    )

    logger.info(
        "parse_pdf finished: %d objects, %d errors, %.0f ms",
        len(result.objects),
        len(result.errors),
        result.processing_time_ms or 0,
    )
    return result


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _dedup_key(obj: DetectedObjectCreate) -> str:
    """Create a dedup key from object type + rounded location."""
    layer = obj.raw_attributes.get("source_layer", "")
    return (
        f"{obj.object_type}|"
        f"{round(obj.location_x or 0, 0)}|"
        f"{round(obj.location_y or 0, 0)}|"
        f"{layer}"
    )


def _dedup_add(
    registry: Dict[str, DetectedObjectCreate],
    obj: DetectedObjectCreate,
) -> None:
    """Insert object into registry, preferring higher confidence on collision."""
    key = _dedup_key(obj)
    existing = registry.get(key)
    if existing is None or obj.confidence > existing.confidence:
        registry[key] = obj
    elif (
        obj.confidence == existing.confidence
        and obj.object_type == "other"
        and existing.object_type == "other"
        and obj.label
        and not existing.label
    ):
        # Prefer the one with a label when both are 'other' and same confidence
        registry[key] = obj


# ---------------------------------------------------------------------------
# Direct execution smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG)

    test_path = (
        Path(__file__).resolve().parents[3]
        / "tests"
        / "fixtures"
        / "sample_floor_plan.pdf"
    )
    filepath = str(test_path) if test_path.exists() else sys.argv[1] if len(sys.argv) > 1 else ""

    if not filepath:
        print("Usage: python -m app.services.pdf_parser <path_to_pdf>")
        print(f"Default test fixture not found at {test_path}")
        sys.exit(1)

    print(f"Parsing: {filepath}")
    result = parse_pdf(filepath)
    print(f"Status: {result.status}")
    print(f"Objects: {len(result.objects)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Time: {result.processing_time_ms:.0f} ms")
    for obj in result.objects:
        print(
            f"  [{obj.object_type:12s}] label={obj.label or '':20s} "
            f"loc=({obj.location_x or 0:8.1f}, {obj.location_y or 0:8.1f}) "
            f"layer={obj.raw_attributes.get('source_layer',''):20s} "
            f"conf={obj.confidence:.1f}"
        )
