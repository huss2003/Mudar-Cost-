"""
Structural sanity checks for uploaded drawing files.

Acts as an "antivirus hook" — ensures the file actually contains
parseable vector content before we commit to the full processing
pipeline.  Files that fail these checks (e.g. scanned-image-only
PDFs) are candidates for the AI vision path instead.

Each check returns ``(is_valid: bool, reason: str)`` so callers can
decide whether to proceed with the CAD/PDF parser or fall back to AI.
"""

from __future__ import annotations

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PDF structural check
# ---------------------------------------------------------------------------


def check_pdf_has_content(filepath: str) -> Tuple[bool, str]:
    """Check whether a PDF contains extractable vector geometry or text.

    Opens the file with PyMuPDF (fitz) and inspects every page for
    vector paths and text.  A PDF that has neither is likely a scanned
    image-only document and should be routed to the AI vision pipeline.

    Parameters
    ----------
    filepath:
        Path to the PDF file on disk.

    Returns
    -------
    Tuple[bool, str]
        ``(True, "Found N vector paths on page M")`` when content is
        found, or ``(False, "reason")`` when the PDF appears empty or
        is unparseable.
    """
    import fitz  # PyMuPDF  -- imported locally to keep the module loadable
    #                            when the dependency isn't installed.

    try:
        doc = fitz.open(filepath)
    except Exception as exc:
        return False, f"PDF parse error: {exc}"

    total_paths = 0
    total_text_chars = 0
    try:
        for page_num, page in enumerate(doc):
            # Check for vector drawings (lines, rects, curves)
            paths = page.get_drawings()
            if paths:
                total_paths += len(paths)
                logger.debug(
                    "Page %d: found %d vector paths",
                    page_num,
                    len(paths),
                )

            # Check for text content
            text = page.get_text()
            if text.strip():
                total_text_chars += len(text.strip())
                logger.debug(
                    "Page %d: found %d chars of text",
                    page_num,
                    len(text.strip()),
                )

        doc.close()

        if total_paths > 0:
            return True, f"Found {total_paths} vector paths across {doc.page_count} page(s)"
        if total_text_chars > 0:
            return (
                True,
                f"Found {total_text_chars} chars of text (no vector content) "
                f"across {doc.page_count} page(s)",
            )

        return (
            False,
            f"PDF ({doc.page_count} page(s)) contains no extractable vector "
            f"geometry or text — appears to be scanned image only",
        )
    except Exception as exc:
        try:
            doc.close()
        except Exception:
            pass
        return False, f"PDF content inspection error: {exc}"


# ---------------------------------------------------------------------------
# DXF structural check
# ---------------------------------------------------------------------------


def check_dxf_has_content(filepath: str) -> Tuple[bool, str]:
    """Check whether a DXF file contains any modelspace entities.

    Opens the file with ezdxf and counts entities in modelspace.
    A DXF with zero entities is effectively empty.

    Parameters
    ----------
    filepath:
        Path to the DXF file on disk.

    Returns
    -------
    Tuple[bool, str]
        ``(True, "DXF: 42 entities, 3 layers")`` when entities exist,
        or ``(False, "reason")`` when the DXF is empty or unparseable.
    """
    import ezdxf

    try:
        doc = ezdxf.readfile(filepath)
    except ezdxf.DXFStructureError as exc:
        return False, f"DXF structure error: {exc}"
    except Exception as exc:
        return False, f"DXF read error: {exc}"

    try:
        modelspace = doc.modelspace()
        # Count all entities (exclude paper space)
        entity_count = 0
        layers: set[str] = set()
        for entity in modelspace:
            entity_count += 1
            if hasattr(entity.dxf, "layer") and entity.dxf.layer:
                layers.add(entity.dxf.layer)

        doc.close()

        if entity_count > 0:
            return (
                True,
                f"DXF: {entity_count} entities, {len(layers)} layer(s)",
            )
        return False, "DXF contains no entities in modelspace"
    except Exception as exc:
        try:
            doc.close()
        except Exception:
            pass
        return False, f"DXF content inspection error: {exc}"


# ---------------------------------------------------------------------------
# DWG structural check (stub — full DWG parsing requires ODA or LibreDWG)
# ---------------------------------------------------------------------------


def check_dwg_has_content(filepath: str) -> Tuple[bool, str]:
    """Check whether a DWG file appears structurally sound.

    Currently only checks the DWG header magic bytes, since full DWG
    parsing requires a licensed SDK (ODA) or LibreDWG (experimental).

    Parameters
    ----------
    filepath:
        Path to the DWG file on disk.

    Returns
    -------
    Tuple[bool, str]
        ``(True, "DWG header valid")`` if the header passes,
        ``(False, "reason")`` otherwise.
    """
    try:
        with open(filepath, "rb") as f:
            header = f.read(32)

        if len(header) < 4:
            return False, "DWG file too small for header"

        # All AutoCAD DWG versions start with AC10xx (AC1015 = R2000, etc.)
        if header[:2] != b"AC":
            return False, f"DWG header invalid: expected 'AC' magic, got {header[:2]!r}"

        return True, "DWG header valid (deep parse requires ODA SDK)"
    except OSError as exc:
        return False, f"DWG read error: {exc}"
