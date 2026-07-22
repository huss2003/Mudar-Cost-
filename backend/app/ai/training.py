"""Training loop utilities: strict detection wrapper and area cross-check.

This module is used **only** during model training / eval iterations.  It must
NEVER fall back to ground truth or mock data when MiMo detection fails —
iterations fail loudly so problems are caught before they pollute results.

Usage
-----
    from app.ai.training import ReraiseMimoVisionClient, validate_detected_area

    client = ReraiseMimoVisionClient()
    try:
        result = client.detect_objects("page_1.png", prompt="...")
        validate_detected_area(result, title_block_area_sqft=1344.0)
    except RuntimeError:
        # Detection failed — iteration aborted
        ...
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.ai.mimo_client import MimoVisionClient, MimoConfig
from app.schemas.detection import DetectedObjectCreate, DetectionResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GU Office floor plan title-block constants
# ---------------------------------------------------------------------------
# The title block on the GU Office floor plan PDF states:
#   24' x 56'1" = 1344 sqft
# This is the expected total floor area against which we cross-check the
# sum of all detected room areas.
#
# Conversion factors used in this module:
#   sqft → sqmm  : multiply by (304.8)² = 92903.04
#   sqmm → sqft  : divide by 92903.04

GU_TITLE_BLOCK_SQFT = 1344.0
GU_TITLE_BLOCK_SQMM = GU_TITLE_BLOCK_SQFT * 92903.04  # ≈ 124_861_685.76 sqmm
AREA_TOLERANCE = 0.10  # ±10%


# ===========================================================================
# 1. Exception-raising wrapper
# ===========================================================================


class ReraiseMimoVisionClient(MimoVisionClient):
    """Training-only wrapper that raises on failure instead of returning a
    ``DetectionResult`` with ``status="failed"``.

    This is the **only** client allowed inside the training loop.  It
    guarantees that any MiMo failure becomes a hard error — no silent
    degradation, no fallback to ground truth, no mock data.

    Parameters
    ----------
    config:
        Optional :class:`MimoConfig`.  The constructor forces
        ``mock_mode=False`` so the training loop never accidentally
        uses mock data.

    Raises
    ------
    RuntimeError
        On any detection failure (network error, parse failure, empty
        response, etc.).
    ValueError
        In production environments when no API key is available.
    """

    def __init__(
        self,
        config: MimoConfig | None = None,
        **kwargs,
    ) -> None:
        # Force mock_mode off — training must use real API
        cfg = config or MimoConfig()
        cfg.mock_mode = False
        super().__init__(config=cfg, **kwargs)

    def detect_objects(
        self,
        image_path: str,
        prompt: str | None = None,
    ) -> DetectionResult:
        """Run detection; raises ``RuntimeError`` on any failure.

        Parameters
        ----------
        image_path : str
            Path to the rasterised PNG image.
        prompt : str | None
            Optional user prompt override.

        Returns
        -------
        DetectionResult
            The successful result (``status == "completed"``).

        Raises
        ------
        RuntimeError
            If MiMo returns ``status="failed"`` or if an unexpected
            exception occurs during detection.
        """
        try:
            result = super().detect_objects(image_path, prompt)
        except Exception as exc:
            raise RuntimeError(
                f"MiMo detection raised an unexpected exception: {exc}"
            ) from exc

        if result.status == "failed":
            errors = "; ".join(result.errors) if result.errors else "unknown error"
            raise RuntimeError(
                f"MiMo detection failed: {errors}"
            )

        if not result.objects:
            raise RuntimeError(
                "MiMo detection returned status='completed' but produced zero objects"
            )

        return result


# ===========================================================================
# 2. Area cross-check against PDF title block
# ===========================================================================


def validate_detected_area(
    result: DetectionResult,
    title_block_area_sqft: float = GU_TITLE_BLOCK_SQFT,
    tolerance: float = AREA_TOLERANCE,
) -> float:
    """Cross-check the sum of detected room/floor areas against the PDF
    title-block dimensions.

    Parameters
    ----------
    result : DetectionResult
        The completed detection result whose objects will be summed.
    title_block_area_sqft : float
        The expected total area from the PDF title block, in square feet.
        Defaults to the GU Office value of 1344 sqft.
    tolerance : float
        Allowed fractional deviation.  Default ±10% (0.10).

    Returns
    -------
    float
        The total detected area in square feet.

    Raises
    ------
    RuntimeError
        If the detected total area differs from the title-block area by
        more than ``tolerance`` (e.g. ±10%).  This prevents the training
        loop from accepting nonsense detections.
    """
    # Sum areas from detected objects that carry an area field
    total_area_sqmm = 0.0
    counted_types: set[str] = set()

    for obj in result.objects:
        if obj.area is not None and obj.area > 0:
            total_area_sqmm += obj.area
            counted_types.add(obj.object_type)

    # Convert to square feet
    total_area_sqft = total_area_sqmm / 92903.04

    logger.info(
        "Area cross-check: detected %.2f sqft (%d objects of types %s) "
        "vs title block %.2f sqft",
        total_area_sqft,
        len([o for o in result.objects if o.area is not None and o.area > 0]),
        sorted(counted_types),
        title_block_area_sqft,
    )

    # Compute deviation
    if total_area_sqft <= 0:
        raise RuntimeError(
            f"Detected total area is zero or negative ({total_area_sqft:.2f} sqft) — "
            "no valid room/floor area detected. Cannot cross-check against "
            f"title block ({title_block_area_sqft:.2f} sqft). "
            "ABORTING training iteration."
        )

    deviation = abs(total_area_sqft - title_block_area_sqft) / title_block_area_sqft

    if deviation > tolerance:
        raise RuntimeError(
            f"Area cross-check FAILED: detected {total_area_sqft:.2f} sqft "
            f"differs from title-block {title_block_area_sqft:.2f} sqft "
            f"by {deviation*100:.1f}% (tolerance ±{tolerance*100:.0f}%). "
            "ABORTING training iteration — detected objects may be nonsense."
        )

    logger.info(
        "Area cross-check PASSED: %.2f sqft vs %.2f sqft (deviation %.1f%%)",
        total_area_sqft,
        title_block_area_sqft,
        deviation * 100,
    )

    return total_area_sqft


# ===========================================================================
# 3. Training iteration helper (no fallback)
# ===========================================================================


def run_training_detection(
    image_paths: List[str],
    prompt: str | None = None,
    title_block_area_sqft: float | None = GU_TITLE_BLOCK_SQFT,
) -> DetectionResult:
    """Run MiMo detection across all image pages with **no fallback**.

    This is the entry point for training-loop detection.  It:
    1. Creates a ``ReraiseMimoVisionClient`` (fails loudly).
    2. Runs MiMo on every page.
    3. Combines objects from all pages.
    4. Optionally validates total area against the PDF title block.

    Parameters
    ----------
    image_paths : list[str]
        One or more rasterised PNG page paths for the same drawing.
    prompt : str | None
        Optional user-prompt override.
    title_block_area_sqft : float | None
        Expected total floor area from the PDF title block, in sqft.
        When *None* the area cross-check is skipped.

    Returns
    -------
    DetectionResult
        Aggregated result with ``status="completed"`` and combined objects
        from all pages.

    Raises
    ------
    RuntimeError
        If any page fails detection or if the area cross-check fails.
    """
    client = ReraiseMimoVisionClient()
    combined: List[DetectedObjectCreate] = []

    for page_idx, img_path in enumerate(image_paths):
        logger.info(
            "Training detection — page %d/%d: %s",
            page_idx + 1,
            len(image_paths),
            img_path,
        )
        page_result = client.detect_objects(img_path, prompt=prompt)

        # The wrapper already guarantees status == "completed" and non-empty
        for obj in page_result.objects:
            obj.source = "ai"
            obj.is_ai_generated = True
            obj.ai_status = "available"
            combined.append(obj)

    final = DetectionResult(
        drawing_id=0,
        status="completed",
        objects=combined,
        errors=[],
        source_format="ai",
    )

    # Area cross-check (if requested)
    if title_block_area_sqft is not None:
        validate_detected_area(final, title_block_area_sqft=title_block_area_sqft)

    return final
