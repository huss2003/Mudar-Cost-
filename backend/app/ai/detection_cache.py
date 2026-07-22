"""sha256-based detection result cache.

The cache stores raw MiMo responses (and the extracted DetectionResult) on
disk, keyed by sha256(file_bytes) of the uploaded PDF.  Cache entries survive
across training iterations so repeated processing of the same drawing re-uses
successful detection results without incurring API cost.

Layout
------
/tmp/work/cache/pdf_<sha256[:12]>/mimo_response.json

The JSON file contains::

    {
        "sha256": "<full hex digest>",
        "created_at": "ISO-8601",
        "status": "completed" | "failed",
        "mimo_raw_response": {...},
        "detection_result": {
            "status": "completed" | "failed",
            "objects": [...],
            "errors": [...]
        }
    }
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.schemas.detection import DetectionResult

logger = logging.getLogger(__name__)

CACHE_ROOT = Path("/tmp/work/cache")


def _pdf_cache_dir(sha256_digest: str) -> Path:
    """Return the cache directory (prefix-based) for a given sha256 hex digest."""
    prefix = sha256_digest[:12]
    return CACHE_ROOT / f"pdf_{prefix}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_sha256(file_bytes: bytes) -> str:
    """Compute the hex SHA-256 digest of *file_bytes*."""
    return hashlib.sha256(file_bytes).hexdigest()


def get_cached_result(
    sha256_digest: str,
) -> Optional[dict[str, Any]]:
    """Return a cached detection result dict, or *None* if no valid cache exists.

    A cache entry is considered valid only when:
    - The file exists, is readable JSON, and its ``status`` is ``"completed"``.
    - The ``sha256`` field inside matches the requested digest.

    Returns *None* when the cache is absent, unparseable, or the stored
    status is ``"failed"`` (so the caller always re-runs on a prior failure).
    """
    cache_dir = _pdf_cache_dir(sha256_digest)
    cache_path = cache_dir / "mimo_response.json"

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r") as f:
            data: dict[str, Any] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cache read error for %s: %s", cache_path, exc)
        return None

    # Verify sha256 integrity
    stored_sha = data.get("sha256", "")
    if stored_sha != sha256_digest:
        logger.warning(
            "Cache sha256 mismatch for %s: expected %s, stored %s",
            cache_path,
            sha256_digest,
            stored_sha,
        )
        return None

    # Only re-use successful detection results
    if data.get("status") != "completed":
        logger.info(
            "Cache entry for %s has status=%r — will re-run detection",
            sha256_digest[:12],
            data.get("status"),
        )
        return None

    logger.info(
        "Cache HIT for sha256=%s (%s objects)",
        sha256_digest[:12],
        len(data.get("detection_result", {}).get("objects", [])),
    )
    return data


def cache_result(
    sha256_digest: str,
    mimo_raw: dict[str, Any],
    detection_result: DetectionResult,
) -> None:
    """Persist a successful MiMo response + DetectionResult to the cache.

    Only caches results where ``detection_result.status == "completed"``.
    Failed results are intentionally **not** cached so the next attempt
    re-runs detection.
    """
    if detection_result.status != "completed":
        logger.info(
            "Not caching failed detection for sha256=%s (status=%s)",
            sha256_digest[:12],
            detection_result.status,
        )
        return

    cache_dir = _pdf_cache_dir(sha256_digest)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "mimo_response.json"

    payload: dict[str, Any] = {
        "sha256": sha256_digest,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "mimo_raw_response": mimo_raw,
        "detection_result": {
            "status": detection_result.status,
            "objects": [o.model_dump() for o in detection_result.objects],
            "errors": detection_result.errors,
        },
    }

    try:
        with open(cache_path, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        logger.info(
            "Cached detection result at %s (sha256=%s, %d objects)",
            cache_path,
            sha256_digest[:12],
            len(detection_result.objects),
        )
    except OSError as exc:
        logger.error("Failed to write cache to %s: %s", cache_path, exc)


def rebuild_detection_from_cache(cache_data: dict[str, Any]) -> Optional[DetectionResult]:
    """Reconstruct a ``DetectionResult`` from cached data.

    Returns *None* if the cached data lacks a valid ``detection_result`` block.
    """
    dr_data = cache_data.get("detection_result")
    if not dr_data or not isinstance(dr_data, dict):
        return None
    try:
        return DetectionResult(**dr_data)
    except Exception as exc:
        logger.warning("Failed to reconstruct DetectionResult from cache: %s", exc)
        return None
