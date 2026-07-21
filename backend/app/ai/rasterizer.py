"""
CAD/PDF rasterizer — renders drawing pages to PNG images for AI vision model input.

Supports:
- DXF files (via ezdxf + matplotlib)
- PDF files (via PyMuPDF / fitz)
- Region-of-interest cropping (via Pillow)
- Automatic format detection by extension
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # noqa: E402 — must be called before other matplotlib imports

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Hard cap on drawing extents (mm) to prevent unreasonably large figures
MAX_EXTENT_MM: float = 1_000_000.0  # 1 km
# Default padding ratio added around the drawing bounds
EXTENT_PADDING: float = 0.05
# Line width for DXF entities in figure points
DXF_LINE_WIDTH: float = 0.5


# ---------------------------------------------------------------------------
# DXF rasterizer
# ---------------------------------------------------------------------------


def rasterize_dxf_page(
    filepath: str,
    page_index: int = 0,
    dpi: int = 150,
    max_size: Tuple[int, int] = (2048, 2048),
) -> str:
    """Render a DXF modelspace page to a temporary PNG file.

    Args:
        filepath: Path to the .dxf file.
        page_index: Ignored for DXF (always modelspace), present for API
                    compatibility with rasterize_pdf_page.
        dpi: Output image resolution in dots per inch.
        max_size: Maximum (width, height) in pixels; the output is scaled
                  down while preserving aspect ratio if it exceeds this.

    Returns:
        Absolute path to the temporary PNG file.

    Raises:
        FileNotFoundError: If *filepath* does not exist.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"DXF file not found: {filepath}")

    import ezdxf
    from ezdxf.math import Vec2

    logger.info("Rasterizing DXF: %s (dpi=%d)", filepath, dpi)

    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()

    # Collect all vector points for computing drawing extents
    points: List[Vec2] = []
    for entity in msp:
        dxftype = entity.dxftype()
        try:
            if dxftype == "LINE":
                points.append(Vec2(entity.dxf.start))
                points.append(Vec2(entity.dxf.end))
            elif dxftype == "LWPOLYLINE":
                for x, y in entity.get_points("xy"):
                    points.append(Vec2(x, y))
            elif dxftype == "CIRCLE":
                center = Vec2(entity.dxf.center)
                radius = entity.dxf.radius
                points.append(center + Vec2(-radius, -radius))
                points.append(center + Vec2(radius, radius))
            elif dxftype == "ARC":
                center = Vec2(entity.dxf.center)
                radius = entity.dxf.radius
                points.append(center + Vec2(-radius, -radius))
                points.append(center + Vec2(radius, radius))
            elif dxftype == "ELLIPSE":
                center = Vec2(entity.dxf.center)
                major = entity.dxf.major_axis  # Vec2 or tuple
                try:
                    mx, my = float(major[0]), float(major[1])
                except (TypeError, IndexError):
                    mx, my = 1.0, 0.0
                radius = (mx**2 + my**2) ** 0.5
                points.append(center + Vec2(-radius, -radius))
                points.append(center + Vec2(radius, radius))
            elif dxftype == "INSERT":
                points.append(Vec2(entity.dxf.insert))
            elif dxftype in ("TEXT", "MTEXT"):
                try:
                    points.append(Vec2(entity.dxf.insert))
                except AttributeError:
                    try:
                        points.append(Vec2(entity.dxf.alignment_point))
                    except AttributeError:
                        pass
            elif dxftype == "POINT":
                points.append(Vec2(entity.dxf.location))
            elif dxftype == "SOLID":
                # Four corners
                for i in range(4):
                    try:
                        corner = getattr(entity.dxf, f"corners_{i}", None)
                        if corner is not None:
                            points.append(Vec2(corner))
                    except (AttributeError, IndexError):
                        pass
            elif dxftype == "SPLINE":
                try:
                    for cp in entity.get_control_points():
                        points.append(Vec2(cp))
                except Exception:
                    pass
            elif dxftype == "POLYLINE":
                try:
                    for v in entity.vertices:
                        points.append(Vec2(v.dxf.location))
                except Exception:
                    pass
            elif dxftype == "HATCH":
                try:
                    for path_data in entity.paths:
                        for p in path_data.vertices:
                            points.append(Vec2(p))
                except Exception:
                    pass
            elif dxftype == "MTEXT":
                try:
                    points.append(Vec2(entity.dxf.insert))
                except AttributeError:
                    pass
            elif dxftype == "DIMENSION":
                pass  # skip dimensions for extent computation
            else:
                # Generic fallback: try insert or location
                try:
                    points.append(Vec2(entity.dxf.insert))
                except AttributeError:
                    try:
                        points.append(Vec2(entity.dxf.location))
                    except AttributeError:
                        pass
        except (AttributeError, TypeError, ValueError, IndexError, Exception):
            # Skip entities that can't be processed
            pass

    # Create the matplotlib figure
    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    try:
        if not points:
            logger.warning("No vector entities found in DXF: %s — returning blank image", filepath)
            # Return a blank white image
            ax.set_xlim(0, 100)
            ax.set_ylim(0, 100)
            ax.set_aspect("equal")
            ax.axis("off")
            out_path = _save_figure(fig, dpi, max_size, "dxf")
            return out_path

        # Compute extents
        xs = [p.x for p in points]
        ys = [p.y for p in points]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)

        # Guard against degenerate / single-point extents
        if abs(x_max - x_min) < 1e-6:
            x_min -= 50
            x_max += 50
        if abs(y_max - y_min) < 1e-6:
            y_min -= 50
            y_max += 50

        # Add padding
        pad_x = (x_max - x_min) * EXTENT_PADDING
        pad_y = (y_max - y_min) * EXTENT_PADDING
        x_min -= pad_x
        x_max += pad_x
        y_min -= pad_y
        y_max += pad_y

        # Cap at MAX_EXTENT_MM
        x_min = max(x_min, -MAX_EXTENT_MM)
        x_max = min(x_max, MAX_EXTENT_MM)
        y_min = max(y_min, -MAX_EXTENT_MM)
        y_max = min(y_max, MAX_EXTENT_MM)

        logger.info(
            "DXF extents: x=[%.1f, %.1f] y=[%.1f, %.1f] (%.0f × %.0f mm)",
            x_min, x_max, y_min, y_max,
            x_max - x_min, y_max - y_min,
        )

        ax.set_xlim(x_min, x_max)
        ax.set_ylim(y_min, y_max)
        ax.set_aspect("equal")
        ax.axis("off")

        # Render each entity onto the axes
        _render_dxf_entities(msp, ax)

        out_path = _save_figure(fig, dpi, max_size, "dxf")
        return out_path
    finally:
        plt.close(fig)
        plt.close("all")


def _render_dxf_entities(msp, ax) -> None:
    """Draw all DXF entities from *msp* onto *ax* using matplotlib."""
    import ezdxf
    from ezdxf.math import Vec2

    for entity in msp:
        dxftype = entity.dxftype()
        try:
            if dxftype == "LINE":
                start = Vec2(entity.dxf.start)
                end = Vec2(entity.dxf.end)
                ax.plot(
                    [start.x, end.x],
                    [start.y, end.y],
                    color="black",
                    linewidth=DXF_LINE_WIDTH,
                )

            elif dxftype == "LWPOLYLINE":
                verts = list(entity.get_points("xy"))
                if len(verts) >= 2:
                    xs = [v[0] for v in verts]
                    ys = [v[1] for v in verts]
                    # Close if the polyline is closed (flags & 1)
                    if entity.closed:
                        xs.append(xs[0])
                        ys.append(ys[0])
                    ax.plot(xs, ys, color="black", linewidth=DXF_LINE_WIDTH)

            elif dxftype == "CIRCLE":
                center = Vec2(entity.dxf.center)
                radius = entity.dxf.radius
                circle = plt.Circle(
                    (center.x, center.y),
                    radius,
                    fill=False,
                    color="black",
                    linewidth=DXF_LINE_WIDTH,
                )
                ax.add_patch(circle)

            elif dxftype == "ARC":
                center = Vec2(entity.dxf.center)
                radius = entity.dxf.radius
                start_angle = entity.dxf.start_angle
                end_angle = entity.dxf.end_angle
                arc = plt.Arc(
                    (center.x, center.y),
                    radius * 2,
                    radius * 2,
                    angle=0.0,
                    theta1=start_angle,
                    theta2=end_angle,
                    color="black",
                    linewidth=DXF_LINE_WIDTH,
                )
                ax.add_patch(arc)

            elif dxftype == "ELLIPSE":
                center = Vec2(entity.dxf.center)
                major = entity.dxf.major_axis
                ratio = entity.dxf.ratio
                try:
                    mx, my = float(major[0]), float(major[1])
                except (TypeError, IndexError):
                    mx, my = 1.0, 0.0
                major_len = (mx**2 + my**2) ** 0.5
                minor_len = major_len * ratio
                angle = float(entity.dxf.extrusion) if hasattr(entity.dxf, "extrusion") else 0.0
                start_param = entity.dxf.start_param if hasattr(entity.dxf, "start_param") else 0.0
                end_param = entity.dxf.end_param if hasattr(entity.dxf, "end_param") else 2 * 3.14159
                ellipse = plt.Arc(
                    (center.x, center.y),
                    major_len * 2,
                    minor_len * 2,
                    angle=0.0,  # simplified
                    theta1=0.0,
                    theta2=360.0,
                    color="black",
                    linewidth=DXF_LINE_WIDTH,
                )
                ax.add_patch(ellipse)

            elif dxftype == "SOLID":
                # Render as filled polygon
                corners = []
                for i in range(4):
                    try:
                        c = getattr(entity.dxf, f"corners_{i}", None)
                        if c is not None:
                            corners.append(Vec2(c))
                    except (AttributeError, IndexError):
                        pass
                if len(corners) >= 3:
                    tri = plt.Polygon(
                        [(p.x, p.y) for p in corners],
                        fill=True,
                        facecolor="black",
                        edgecolor="black",
                        linewidth=DXF_LINE_WIDTH / 2,
                    )
                    ax.add_patch(tri)

            elif dxftype == "SPLINE":
                try:
                    pts = [Vec2(cp) for cp in entity.get_control_points()]
                    if len(pts) >= 2:
                        xs = [p.x for p in pts]
                        ys = [p.y for p in pts]
                        ax.plot(xs, ys, color="black", linewidth=DXF_LINE_WIDTH)
                except Exception:
                    pass

            elif dxftype == "POLYLINE":
                try:
                    verts = [Vec2(v.dxf.location) for v in entity.vertices]
                    if len(verts) >= 2:
                        xs = [v.x for v in verts]
                        ys = [v.y for v in verts]
                        if entity.dxf.flags & 1:  # closed polyline
                            xs.append(xs[0])
                            ys.append(ys[0])
                        ax.plot(xs, ys, color="black", linewidth=DXF_LINE_WIDTH)
                except Exception:
                    pass

            elif dxftype in ("TEXT", "MTEXT"):
                try:
                    text = entity.dxf.text if dxftype == "TEXT" else getattr(entity, "text", "")
                    try:
                        insert = Vec2(entity.dxf.insert)
                    except AttributeError:
                        insert = Vec2(0, 0)
                    if text:
                        ax.text(
                            insert.x,
                            insert.y,
                            str(text),
                            fontsize=3,
                            color="black",
                            clip_on=True,
                        )
                except Exception:
                    pass

            elif dxftype == "INSERT":
                # Render insert as a small cross marker (block reference)
                try:
                    insert = Vec2(entity.dxf.insert)
                    ax.plot(insert.x, insert.y, "k+", markersize=2)
                except Exception:
                    pass

            elif dxftype == "POINT":
                try:
                    loc = Vec2(entity.dxf.location)
                    ax.plot(loc.x, loc.y, "k.", markersize=1)
                except Exception:
                    pass

            elif dxftype == "HATCH":
                # Render hatch boundary paths
                try:
                    for path_data in entity.paths:
                        verts = [Vec2(p) for p in path_data.vertices]
                        if len(verts) >= 3:
                            poly = plt.Polygon(
                                [(p.x, p.y) for p in verts],
                                fill=True,
                                facecolor="lightgray",
                                edgecolor="black",
                                linewidth=DXF_LINE_WIDTH / 2,
                            )
                            ax.add_patch(poly)
                except Exception:
                    pass

            # DIMENSION and other annotation types are skipped intentionally
        except (AttributeError, TypeError, ValueError, IndexError, Exception) as exc:
            logger.debug("Skipping %s entity: %s", dxftype, exc)
            continue


# ---------------------------------------------------------------------------
# PDF rasterizer
# ---------------------------------------------------------------------------


def rasterize_pdf_page(
    filepath: str,
    page_index: int = 0,
    dpi: int = 150,
    max_size: Tuple[int, int] = (2048, 2048),
) -> str:
    """Render a single PDF page to a temporary PNG file.

    Args:
        filepath: Path to the .pdf file.
        page_index: Zero-based page number to render.
        dpi: Output image resolution in dots per inch.
        max_size: Maximum (width, height) in pixels; the pixmap is scaled
                  down while preserving aspect ratio if it exceeds this.

    Returns:
        Absolute path to the temporary PNG file.

    Raises:
        FileNotFoundError: If *filepath* does not exist.
        IndexError: If *page_index* is out of range.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {filepath}")

    import fitz  # PyMuPDF

    logger.info("Rasterizing PDF: %s page=%d dpi=%d", filepath, page_index, dpi)

    doc = fitz.open(str(path))
    try:
        if page_index < 0 or page_index >= len(doc):
            raise IndexError(
                f"Page index {page_index} out of range for "
                f"{filepath} ({len(doc)} pages)"
            )

        page = doc[page_index]
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix)

        # Scale down if pixmap exceeds max_size
        pw, ph = pix.width, pix.height
        if pw > max_size[0] or ph > max_size[1]:
            scale = min(max_size[0] / pw, max_size[1] / ph)
            new_w = int(pw * scale)
            new_h = int(ph * scale)
            logger.info(
                "Scaling PDF pixmap %dx%d → %dx%d (factor=%.3f)",
                pw, ph, new_w, new_h, scale,
            )
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom * scale, zoom * scale))
            pw, ph = pix.width, pix.height

        logger.info("PDF pixmap size: %dx%d pixels (%.1f KB)", pw, ph, len(pix.samples) / 1024)

        out_path = _temp_png_path("pdf")
        pix.save(out_path)
        logger.info("Saved PDF raster: %s", out_path)
        return out_path
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Region cropper
# ---------------------------------------------------------------------------


def rasterize_region(
    image_path: str,
    bbox: Tuple[float, float, float, float],
    output_path: Optional[str] = None,
) -> str:
    """Crop a region of interest from an existing rasterized image.

    Args:
        image_path: Path to an existing PNG (or any PIL-compatible image).
        bbox: Crop box as (x1, y1, x2, y2) in pixel coordinates.
        output_path: Destination path for the cropped PNG. If ``None``, a new
                     temporary file is created.

    Returns:
        Absolute path to the cropped PNG file.

    Raises:
        FileNotFoundError: If *image_path* does not exist.
    """
    from PIL import Image

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    x1, y1, x2, y2 = bbox
    # Clamp to pixel boundaries
    x1, y1 = max(0, round(x1)), max(0, round(y1))
    x2, y2 = round(x2), round(y2)

    if x2 <= x1 or y2 <= y1:
        raise ValueError(
            f"Invalid bbox: ({x1}, {y1}, {x2}, {y2}) — "
            f"width={x2 - x1}, height={y2 - y1}; both must be > 0"
        )

    img = Image.open(str(path))
    cropped = img.crop((x1, y1, x2, y2))

    if output_path:
        dest = Path(output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
    else:
        dest = Path(_temp_png_path("crop"))

    cropped.save(str(dest), "PNG")
    file_size = dest.stat().st_size
    logger.info(
        "Cropped region %s (%d×%d) from %s → %s (%.1f KB)",
        str(bbox), x2 - x1, y2 - y1, image_path, dest, file_size / 1024,
    )
    return str(dest.resolve())


# ---------------------------------------------------------------------------
# Auto-detecting entry point
# ---------------------------------------------------------------------------


def rasterize_drawing(filepath: str, dpi: int = 150) -> List[str]:
    """Render a CAD or PDF drawing to one or more PNG images.

    Detects the format from the file extension (``.dxf`` or ``.pdf``).

    - For DXF files, the single modelspace page is rendered.
    - For PDF files, **every** page is rendered and returned as a separate PNG.

    Args:
        filepath: Path to the drawing file.
        dpi: Output resolution in dots per inch.

    Returns:
        List of absolute paths to the temporary PNG files (one per page).

    Raises:
        FileNotFoundError: If *filepath* does not exist.
        ValueError: If the file extension is not recognised.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Drawing file not found: {filepath}")

    suffix = path.suffix.lower()

    if suffix == ".dxf":
        return [rasterize_dxf_page(filepath, dpi=dpi)]

    if suffix == ".pdf":
        import fitz

        doc = fitz.open(str(path))
        num_pages = len(doc)
        doc.close()

        pages: List[str] = []
        for i in range(num_pages):
            png_path = rasterize_pdf_page(filepath, page_index=i, dpi=dpi)
            pages.append(png_path)
        return pages

    raise ValueError(
        f"Unrecognised drawing format: '{suffix}'. "
        f"Supported formats: .dxf, .pdf"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _temp_png_path(prefix: str = "drawing") -> str:
    """Return an absolute path to a new temporary PNG file."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png", prefix=f"{prefix}_")
    path = tmp.name
    tmp.close()
    return path


def _save_figure(
    fig: matplotlib.figure.Figure,
    dpi: int,
    max_size: Tuple[int, int],
    prefix: str = "drawing",
) -> str:
    """Save a matplotlib figure to a temporary PNG file.

    Handles dimension capping and file-size logging.
    """
    out_path = _temp_png_path(prefix)
    fig.savefig(
        out_path,
        dpi=dpi,
        bbox_inches="tight",
        pad_inches=0.1,
        facecolor="white",
        edgecolor="none",
    )
    file_size = Path(out_path).stat().st_size
    # Check actual image dimensions via Pillow
    from PIL import Image

    with Image.open(out_path) as img:
        actual_w, actual_h = img.size
    logger.info(
        "Saved DXF raster: %s (%d×%d px, %.1f KB, dpi=%d)",
        out_path, actual_w, actual_h, file_size / 1024, dpi,
    )

    # Downscale if actual dimensions exceed max_size
    if actual_w > max_size[0] or actual_h > max_size[1]:
        scale = min(max_size[0] / actual_w, max_size[1] / actual_h)
        new_w = int(actual_w * scale)
        new_h = int(actual_h * scale)
        logger.info("Downscaling raster %d×%d → %d×%d", actual_w, actual_h, new_w, new_h)
        with Image.open(out_path) as img:
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            resized.save(out_path, "PNG")
        logger.info("Resaved downscaled raster: %s", out_path)

    return str(Path(out_path).resolve())
