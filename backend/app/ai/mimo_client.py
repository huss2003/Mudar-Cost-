"""MiMo v2.5 Vision API client wrapper.

Features
--------
- Circuit breaker, structured logging, retry, and model registry.
- Mock mode gated on ``mock=True`` OR ``ENVIRONMENT="development"``.
- **Production safety**: raises ``ValueError`` at construction when the
  API key is missing and the environment is **not** development.
"""

from __future__ import annotations

import base64
import io
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
import structlog
from PIL import Image

from app.ai.circuit_breaker import CircuitBreaker
from app.ai.models import ModelSpec, get_model, ModelCapability
from app.config import settings
from app.schemas.detection import DetectedObjectCreate, DetectionResult
from app.services.metrics import ai_calls, mock_mode_fallback
from app.services.trace import get_trace_id

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Default system / user prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a CAD drawing analyzer. Return ONLY valid JSON. "
    "Analyze the drawing and list every visible object with its "
    "bounding box and label."
)

_USER_PROMPT_TEMPLATE = (
    "List all visible objects in this CAD drawing. For each object "
    "return: object_type, label, bbox (x1,y1,x2,y2 as fractions 0-1), "
    "confidence. Types: wall, glass, partition, cabin, meeting_room, "
    "door, window, ceiling, floor, column, furniture, electrical_symbol, "
    "hvac_symbol, stair, other. Return JSON array with keys: object_type, "
    "label, bbox, confidence."
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class MimoConfig:
    """Configuration for the MiMo v2.5 Vision API client."""

    api_key: str = ""  # Set explicitly or auto-resolved from env
    endpoint: str = "https://api.xiaomimimo.com/v1/chat/completions"
    model_key: str = "mimo-v2.5"
    max_retries: int = 3
    timeout_seconds: int = 60
    rate_per_image: float = 0.003  # USD estimate per API call
    max_image_size: tuple[int, int] = (1024, 1024)
    mock_mode: bool = False
    # Conversion from fractional bbox to mm
    dpi: float = 96.0
    drawing_scale: float = 100.0  # e.g. 1:100 → multiply mm by 100


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------


class MimoVisionClient:
    """Client for the MiMo v2.5 vision-language API.

    Parameters
    ----------
    config:
        Optional :class:`MimoConfig`.  When *None* defaults are used.
    circuit_breaker:
        Shared circuit-breaker instance.  A fresh one is created when
        *None* is passed.

    Raises
    ------
    ValueError
        In production environments when no API key is available.
    """

    def __init__(
        self,
        config: MimoConfig | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.config = config or MimoConfig()
        self._breaker = circuit_breaker or CircuitBreaker()

        # Resolve API key from explicit config → env
        api_key = self.config.api_key or settings.MIMO_API_KEY or ""
        self.config.api_key = api_key

        # Resolve mock mode
        is_dev = settings.ENVIRONMENT in ("dev", "development")
        if self.config.mock_mode:
            pass  # explicitly asked for mock
        elif is_dev and not api_key:
            self.config.mock_mode = True
            logger.info("MiMo mock mode auto-enabled (dev environment, no key)")
            mock_mode_fallback.labels(
                provider="mimo",
                model=self.config.model_key,
            ).inc()
        elif not is_dev and not api_key:
            raise ValueError(
                "MIMO_API_KEY is not set and ENVIRONMENT is not 'development'. "
                "Cannot run in production without an API key."
            )

        # Validate model
        try:
            self._spec: ModelSpec = get_model(self.config.model_key)
        except ValueError:
            # Fall back gracefully — unknown model key but still let it run
            self._spec = ModelSpec(
                name=self.config.model_key,
                provider="unknown",
                capability=ModelCapability.VISION,
                max_tokens=128000,
                cost_per_1k_input=0.0,
                cost_per_1k_output=0.0,
                supports_vision=True,
            )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def detect_objects(
        self,
        image_path: str,
        prompt: str | None = None,
    ) -> DetectionResult:
        """Detect objects in a drawing image.

        Parameters
        ----------
        image_path:
            Path to the image file (PNG, JPEG, …).
        prompt:
            Optional user prompt override.  When *None* the built-in
            ``_USER_PROMPT_TEMPLATE`` is used.

        Returns
        -------
        DetectionResult
            Normalised result (may carry ``status="failed"`` on error).
        """
        if self.config.mock_mode:
            return self._mock_detect(prompt)
        return self._breaker.call(
            self._real_detect,
            image_path,
            prompt,
        )

    # ------------------------------------------------------------------
    # Mock mode
    # ------------------------------------------------------------------

    def _mock_detect(self, prompt: str | None = None) -> DetectionResult:
        """Return a canned ``DetectionResult`` without calling the API."""
        objects: list[DetectedObjectCreate] = [
            DetectedObjectCreate(
                object_type="wall",
                label="Wall-1",
                length=5000.0,
                width=200.0,
                bbox_coords=[0.0, 0.0, 5000.0, 200.0],
                confidence=0.95,
                source="ai",
            ),
            DetectedObjectCreate(
                object_type="door",
                label="Door-1",
                width=900.0,
                bbox_coords=[1000.0, 0.0, 1900.0, 200.0],
                confidence=0.90,
                source="ai",
            ),
            DetectedObjectCreate(
                object_type="window",
                label="Window-1",
                width=2000.0,
                bbox_coords=[2000.0, 0.0, 4000.0, 200.0],
                confidence=0.92,
                source="ai",
            ),
        ]

        if prompt and "room" in prompt.lower():
            objects.append(
                DetectedObjectCreate(
                    object_type="other",
                    label="Room-1",
                    confidence=0.85,
                    source="ai",
                ),
            )

        result = DetectionResult(
            drawing_id=0,
            status="completed",
            objects=objects,
            source_format="ai",
        )

        logger.info(
            "ai_call",
            model=self.config.model_key,
            latency_ms=0,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=0.0,
            status="mock",
            object_count=len(objects),
            trace_id=get_trace_id(),
        )

        ai_calls.labels(
            provider="mimo",
            model=self.config.model_key,
            outcome="mock",
        ).inc()
        return result

    # ------------------------------------------------------------------
    # Real API call
    # ------------------------------------------------------------------

    def _real_detect(
        self,
        image_path: str,
        prompt: str | None = None,
    ) -> DetectionResult:
        """Execute the full vision API pipeline with retry."""
        start = time.monotonic()

        # 1. Load & prepare image ------------------------------------------
        try:
            img = Image.open(image_path)
            img = img.copy()  # force full load before file handle closes
            img = self._resize_image(img)
        except FileNotFoundError:
            logger.error("Image not found", path=image_path)
            return DetectionResult(
                drawing_id=0,
                status="failed",
                errors=[f"Image not found: {image_path}"],
                source_format="ai",
            )
        except Exception as exc:
            logger.error("Failed to open image", path=image_path, error=str(exc))
            return DetectionResult(
                drawing_id=0,
                status="failed",
                errors=[f"Image read error: {exc}"],
                source_format="ai",
            )

        # Encode to base64 PNG
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        # 2. Build messages -------------------------------------------------
        user_text = prompt or _USER_PROMPT_TEMPLATE
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64}",
                        },
                    },
                ],
            },
        ]

        # 3. Retry loop ----------------------------------------------------
        last_error: str | None = None
        total_tokens = 0
        call_count = 0

        for attempt in range(1, self.config.max_retries + 1):
            call_count = attempt
            try:
                resp = requests.post(
                    self.config.endpoint,
                    headers={
                        "api-key": self.config.api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.config.model_key,
                        "messages": messages,
                        "max_tokens": 8192,
                    },
                    timeout=self.config.timeout_seconds,
                )
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()

                total_tokens = (
                    data.get("usage", {}).get("total_tokens", 0) or 0
                )

                content: str = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )

                objects_data = self._parse_objects_json(content)
                objects = [
                    self._build_detected_object(obj, img.width, img.height)
                    for obj in objects_data
                ]

                latency_ms = (time.monotonic() - start) * 1000
                prompt_tokens = data.get("usage", {}).get("prompt_tokens", 0) or 0
                completion_tokens = data.get("usage", {}).get("completion_tokens", 0) or 0
                cost_usd = (
                    (prompt_tokens * self._spec.cost_per_1k_input)
                    + (completion_tokens * self._spec.cost_per_1k_output)
                ) / 1000.0

                logger.info(
                    "ai_call",
                    model=self.config.model_key,
                    latency_ms=round(latency_ms, 1),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=round(cost_usd, 6),
                    status="success",
                    object_count=len(objects),
                    trace_id=get_trace_id(),
                )

                ai_calls.labels(
                    provider="mimo",
                    model=self.config.model_key,
                    outcome="success",
                ).inc()

                return DetectionResult(
                    drawing_id=0,
                    status="completed",
                    objects=objects,
                    source_format="ai",
                )

            except requests.exceptions.Timeout:
                last_error = f"Request timed out after {self.config.timeout_seconds}s"
                logger.warning(
                    "MiMo attempt %d/%d timed out",
                    attempt,
                    self.config.max_retries,
                )
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "?"
                body = (
                    exc.response.text[:500]
                    if exc.response is not None
                    else ""
                )
                last_error = f"HTTP {status}: {body}"
                logger.warning(
                    "MiMo attempt %d/%d HTTP error: %s",
                    attempt,
                    self.config.max_retries,
                    last_error,
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.RequestException) as exc:
                last_error = f"Request failed: {exc}"
                logger.warning(
                    "MiMo attempt %d/%d connection error: %s",
                    attempt,
                    self.config.max_retries,
                    exc,
                )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                last_error = f"Response parse error: {exc}"
                logger.warning(
                    "MiMo attempt %d/%d parse error: %s",
                    attempt,
                    self.config.max_retries,
                    exc,
                )
            except Exception as exc:
                last_error = f"Unexpected error: {exc}"
                logger.warning(
                    "MiMo attempt %d/%d unexpected error: %s",
                    attempt,
                    self.config.max_retries,
                    exc,
                )

            if attempt < self.config.max_retries:
                delay = 2 ** (attempt - 1)
                logger.info("Retrying in %ds ...", delay)
                time.sleep(delay)

        # All retries exhausted
        latency_ms = (time.monotonic() - start) * 1000
        logger.error(
            "ai_call",
            model=self.config.model_key,
            latency_ms=round(latency_ms, 1),
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=0.0,
            status="failed",
            error=last_error,
            trace_id=get_trace_id(),
        )

        ai_calls.labels(
            provider="mimo",
            model=self.config.model_key,
            outcome="failed",
        ).inc()
        return DetectionResult(
            drawing_id=0,
            status="failed",
            errors=[f"MiMo API failed after {self.config.max_retries} retries: {last_error}"],
            source_format="ai",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resize_image(self, img: Image.Image) -> Image.Image:
        """Resize *img* to fit within ``self.config.max_image_size``, aspect-ratio kept."""
        max_w, max_h = self.config.max_image_size
        img.thumbnail((max_w, max_h), Image.LANCZOS)
        return img

    @staticmethod
    def _parse_objects_json(content: str) -> list[dict[str, Any]]:
        """Extract a JSON array of objects from the LLM response.

        Handles responses wrapped in ```json … ``` markdown blocks,
        leading/trailing text, and malformed-but-recoverable JSON.
        Returns an empty list on total parse failure.
        """
        if not content or not content.strip():
            return []

        text = content.strip()

        # Try direct parse first
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                for key in ("objects", "items", "results", "data"):
                    if key in parsed and isinstance(parsed[key], list):
                        return parsed[key]
                if any(k in parsed for k in ("object_type", "label", "bbox")):
                    return [parsed]
            return []
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        code_match = re.search(
            r"```(?:json)?\s*\n?(.*?)\n?```",
            text,
            re.DOTALL,
        )
        if code_match:
            try:
                parsed = json.loads(code_match.group(1).strip())
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict):
                    for key in ("objects", "items", "results", "data"):
                        if key in parsed and isinstance(parsed[key], list):
                            return parsed[key]
                    return [parsed]
            except json.JSONDecodeError:
                pass

        # Last resort: try to find a JSON array with \[...\] regex
        array_match = re.search(r"\[[\s\S]*\]", text)
        if array_match:
            try:
                parsed = json.loads(array_match.group(0))
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        return []

    def _build_detected_object(
        self,
        obj_data: dict[str, Any],
        img_width: int,
        img_height: int,
    ) -> DetectedObjectCreate:
        """Map a parsed API object dict to a ``DetectedObjectCreate``.

        Converts fractional bounding-box coordinates to millimetres
        using the configured DPI and drawing scale.
        """
        bbox_frac = obj_data.get("bbox")
        bbox_mm = self._fractional_to_mm(bbox_frac, img_width, img_height)

        return DetectedObjectCreate(
            object_type=obj_data.get("object_type", "other"),
            label=obj_data.get("label"),
            length=obj_data.get("length"),
            width=obj_data.get("width"),
            area=obj_data.get("area"),
            height=obj_data.get("height"),
            thickness=obj_data.get("thickness"),
            bbox_coords=bbox_mm,
            confidence=float(obj_data.get("confidence", 0.8)),
            source="ai",
        )

    def _fractional_to_mm(
        self,
        bbox: Any,
        img_width: int,
        img_height: int,
    ) -> list[float] | None:
        """Convert a fractional bounding box ``[x1, y1, x2, y2]`` to mm.

        Formula::

            mm_per_pixel = 25.4 / dpi
            mm = frac * pixel_dim * mm_per_pixel * drawing_scale

        Returns ``None`` if *bbox* is missing or not a 4-element sequence.
        """
        if not bbox or not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
            return None

        mm_per_px = (25.4 / self.config.dpi) * self.config.drawing_scale

        x1 = float(bbox[0]) * img_width * mm_per_px
        y1 = float(bbox[1]) * img_height * mm_per_px
        x2 = float(bbox[2]) * img_width * mm_per_px
        y2 = float(bbox[3]) * img_height * mm_per_px

        return [x1, y1, x2, y2]
