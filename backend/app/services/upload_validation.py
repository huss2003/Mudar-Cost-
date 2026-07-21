"""
File upload validation service.

Provides reusable validation for uploaded files — checks file extension,
size limits, magic bytes, SHA-256 dedup, filename sanitization, and EXIF
stripping — and returns structured error messages rather than raising HTTP
exceptions directly, so callers (routers or services) can decide how to respond.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Optional

from PIL import Image

# ---------------------------------------------------------------------------
# Allowed extensions
# ---------------------------------------------------------------------------
ALLOWED_CAD_EXTENSIONS = {".dwg", ".dxf", ".pdf"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# ---------------------------------------------------------------------------
# Size limits
# ---------------------------------------------------------------------------
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB  — CAD / PDF files
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB  — images (thumbnails, photos)

# ---------------------------------------------------------------------------
# Magic bytes for MIME validation
# ---------------------------------------------------------------------------
MAGIC_BYTES: dict[str, bytes] = {
    ".pdf": b"%PDF",
    ".dwg": b"AC10",  # AutoCAD 2000+ binary DWG header
    ".dxf": b"",      # DXF is text-based — handled separately below
}


def check_magic_bytes(filename: str, header: bytes) -> Optional[str]:
    """Verify that the file header matches the declared extension.

    Parameters
    ----------
    filename:
        Original filename whose extension we trust as the declared type.
    header:
        First few bytes of the file (at least 64 bytes recommended).

    Returns
    -------
    str | None
        ``None`` when the magic bytes match.  An error message when they
        don't, which the caller can wrap into an HTTP 400 response.
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_CAD_EXTENSIONS and ext not in ALLOWED_IMAGE_EXTENSIONS:
        return None  # extension itself will be caught by validate_upload_file

    if ext == ".dxf":
        # DXF text format starts with whitespace then "SECTION"
        # (binary DXF starts with \x00 then "SECTION")
        if b"SECTION" not in header[:50]:
            return (
                f"File claims .dxf but does not contain expected DXF header "
                f"(no 'SECTION' found in first 50 bytes)"
            )
    elif ext == ".dwg":
        if not header[:4] == b"AC10":
            return (
                f"File claims .dwg but does not contain expected DWG header "
                f"(expected 'AC10' at offset 0, got {header[:4]!r})"
            )
    elif ext == ".pdf":
        if not header[:4] == b"%PDF":
            return (
                f"File claims .pdf but does not contain expected PDF header "
                f"(expected '%PDF' at offset 0, got {header[:4]!r})"
            )
    elif ext in ALLOWED_IMAGE_EXTENSIONS:
        # Basic image magic-byte check
        if ext == ".png" and not header[:8] == b"\x89PNG\r\n\x1a\n":
            return "File claims .png but does not contain a valid PNG header"
        if ext in (".jpg", ".jpeg") and not header[:2] == b"\xff\xd8":
            return "File claims .jpg/.jpeg but does not contain a valid JPEG header"
        if ext == ".webp" and header[0:4] != b"RIFF":
            return "File claims .webp but does not contain a valid WebP header"

    return None


# ---------------------------------------------------------------------------
# SHA-256 hash
# ---------------------------------------------------------------------------


def file_hash(content: bytes) -> str:
    """Return the SHA-256 hex digest of *content*."""
    return hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# EXIF stripping
# ---------------------------------------------------------------------------


def strip_exif(filepath: str) -> None:
    """Remove EXIF metadata from image files in-place.

    Opens the image at *filepath*, rebuilds it without EXIF data, and
    overwrites the original file.  Safe for JPEG, PNG, and WebP.

    Parameters
    ----------
    filepath:
        Absolute or relative path to the image file.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return  # not an image — nothing to strip

    img = Image.open(filepath)
    # Rebuild the image — strips all EXIF/metadata
    data = list(img.getdata())
    img_no_exif = Image.new(img.mode, img.size)
    img_no_exif.putdata(data)

    # Preserve the original format
    save_format = img.format or "JPEG"
    img_no_exif.save(filepath, format=save_format)
    img.close()


# ---------------------------------------------------------------------------
# Filename sanitization
# ---------------------------------------------------------------------------

_FILENAME_CLEAN_RE = re.compile(r'[\\/:*?"<>|]')


def sanitize_filename(filename: str) -> str:
    """Remove path-traversal characters and normalise a user-supplied filename.

    * Removes directory separators and dangerous characters.
    * Strips empty / dot / dot-dot / all-dots path components.
    * Falls back to ``"uploaded_file"`` if the result would be empty.

    Parameters
    ----------
    filename:
        Original filename from the upload form.

    Returns
    -------
    str
        A safe, clean filename.
    """
    # Replace any dangerous characters with underscores
    name = _FILENAME_CLEAN_RE.sub("_", filename)

    # Split on underscores (which replaced separators) and drop empty / dot parts
    parts = [p for p in name.split("_") if p not in ("", ".", "..")]
    # Strip anything that is purely dots (e.g. "....")
    parts = [p for p in parts if not set(p).issubset({"."})]

    return "_".join(parts) if parts else "uploaded_file"


# ---------------------------------------------------------------------------
# Extension + size validation (existing)
# ---------------------------------------------------------------------------


def validate_upload_file(filename: str, file_size: int) -> str | None:
    """Validate a file's extension and size.

    Parameters
    ----------
    filename:
        The original name of the uploaded file (used to extract the
        extension).
    file_size:
        The file size in bytes (must already be known, e.g. after reading
        or from ``Content-Length``).

    Returns
    -------
    str | None
        ``None`` when the file is valid.  An error message string when
        validation fails — the caller can wrap it into an HTTP 400 or
        include it in a batch response.
    """
    # 1. Extract and normalise the extension
    ext = os.path.splitext(filename)[1].lower()

    # 2. Check extension is in the allowed set
    allowed = ALLOWED_CAD_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS
    if ext not in allowed:
        return (
            f"Unsupported file type: {ext}. "
            f"Allowed types: {', '.join(sorted(allowed))}"
        )

    # 3. Size check — images have a tighter limit
    max_sz = MAX_FILE_SIZE if ext in ALLOWED_CAD_EXTENSIONS else MAX_IMAGE_SIZE
    if file_size > max_sz:
        return (
            f"File too large: {file_size / 1024 / 1024:.1f} MB "
            f"> {max_sz / 1024 / 1024:.0f} MB"
        )

    # All checks passed
    return None
