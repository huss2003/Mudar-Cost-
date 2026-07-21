"""Contract tests for AI providers.

These tests call the **real** MiMo and DeepSeek APIs to verify that
the response shape matches the expected schema.

Gating
------
- Set ``RUN_CONTRACT_TESTS=1`` to enable.
- Each provider's API key must be set in the environment or ``.env``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Mark: only run when explicitly asked
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_CONTRACT_TESTS", "0") != "1",
    reason="Contract tests are gated behind RUN_CONTRACT_TESTS=1",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).resolve().parent


def _log_contract_result(
    provider: str,
    model: str,
    elapsed_ms: float,
    status: str,
    detail: str = "",
) -> None:
    """Log a contract-test result in structured format."""
    logger.info(
        "contract_test",
        provider=provider,
        model=model,
        latency_ms=round(elapsed_ms, 1),
        status=status,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# MiMo Vision contract tests
# ---------------------------------------------------------------------------


class TestMimoContract:
    """Contract tests for the MiMo v2.5 Vision API."""

    @pytest.fixture(scope="class")
    def mimo_client(self):
        """Lazy import to avoid import errors when deps missing."""
        from app.ai.mimo_client import MimoVisionClient, MimoConfig

        api_key = os.environ.get("MIMO_API_KEY", "")
        if not api_key:
            pytest.skip("MIMO_API_KEY not set — skipping MiMo contract test")
        return MimoVisionClient(MimoConfig(api_key=api_key))

    @pytest.fixture(scope="class")
    def sample_image(self) -> Path:
        """Return a small test image for vision API calls."""
        img = _BASE_DIR / "fixtures" / "test_drawing.png"
        if not img.exists():
            # Create a minimal placeholder
            from PIL import Image

            img.parent.mkdir(parents=True, exist_ok=True)
            im = Image.new("RGB", (400, 300), color="white")
            im.save(str(img), format="PNG")
        return img

    def test_vision_response_shape(self, mimo_client, sample_image: Path) -> None:
        """Real MiMo call returns a ``DetectionResult`` with expected fields."""
        from app.schemas.detection import DetectionResult

        start = time.monotonic()
        result = mimo_client.detect_objects(str(sample_image))
        elapsed = (time.monotonic() - start) * 1000

        assert isinstance(result, DetectionResult), (
            f"Expected DetectionResult, got {type(result).__name__}"
        )
        assert result.status in ("completed", "failed"), (
            f"Unexpected status: {result.status}"
        )

        _log_contract_result(
            provider="opencodego",
            model="mimo-v2.5",
            elapsed_ms=elapsed,
            status=result.status,
            detail=f"objects={len(result.objects)}",
        )

        if result.status == "completed":
            assert result.source_format == "ai"
            for obj in result.objects:
                assert obj.object_type, "object_type must be non-empty"
                assert obj.confidence > 0, "confidence must be positive"
                assert obj.source == "ai"

    def test_vision_error_on_bad_path(self, mimo_client) -> None:
        """Real client returns a failed result for a non-existent file."""
        start = time.monotonic()
        result = mimo_client.detect_objects("/nonexistent/path.png")
        elapsed = (time.monotonic() - start) * 1000

        assert result.status == "failed"
        assert len(result.errors) > 0

        _log_contract_result(
            provider="opencodego",
            model="mimo-v2.5",
            elapsed_ms=elapsed,
            status=result.status,
            detail="bad_path",
        )


# ---------------------------------------------------------------------------
# DeepSeek Text contract tests
# ---------------------------------------------------------------------------


class TestDeepSeekContract:
    """Contract tests for the DeepSeek V4 Flash API."""

    @pytest.fixture(scope="class")
    def ds_client(self):
        """Lazy import to avoid import errors when deps missing."""
        from app.ai.deepseek_client import DeepSeekClient, DeepSeekConfig

        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            pytest.skip("DEEPSEEK_API_KEY not set — skipping DeepSeek contract test")
        return DeepSeekClient(DeepSeekConfig(api_key=api_key))

    @pytest.mark.asyncio
    async def test_text_response_shape(self, ds_client) -> None:
        """Real DeepSeek call returns the expected dict shape."""
        start = time.monotonic()
        result = await ds_client.ask(
            messages=[{"role": "user", "content": "Say 'hello world'"}],
            temperature=0.0,
        )
        elapsed = (time.monotonic() - start) * 1000

        # Top-level keys
        assert "choices" in result, "Response missing 'choices'"
        assert "usage" in result, "Response missing 'usage'"

        choice = result["choices"][0]
        assert "message" in choice, "Choice missing 'message'"
        msg = choice["message"]
        assert "content" in msg, "Message missing 'content'"

        usage = result["usage"]
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage

        _log_contract_result(
            provider="opencodego",
            model="deepseek-v4-flash",
            elapsed_ms=elapsed,
            status="success" if "error" not in result else result.get("error", "unknown"),
            detail=f"prompt={usage.get('prompt_tokens')} "
            f"completion={usage.get('completion_tokens')}",
        )

    @pytest.mark.asyncio
    async def test_tool_call_shape(self, ds_client) -> None:
        """Real DeepSeek call with tools returns tool_calls in the response."""
        from app.ai.deepseek_client import TOOLS

        start = time.monotonic()
        result = await ds_client.ask(
            messages=[{"role": "user", "content": "Get project BOQ for project 42"}],
            tools=TOOLS,
            temperature=0.0,
        )
        elapsed = (time.monotonic() - start) * 1000

        # The model may either respond with content or tool_calls — both are valid
        assert "choices" in result
        msg = result["choices"][0].get("message", {})

        has_tool_calls = "tool_calls" in msg and msg["tool_calls"] is not None
        has_content = msg.get("content") is not None

        assert has_tool_calls or has_content, (
            "Response should have either content or tool_calls"
        )

        if has_tool_calls:
            tc = msg["tool_calls"][0]
            assert tc["type"] == "function"
            assert "function" in tc
            assert "name" in tc["function"]
            assert "arguments" in tc["function"]
            # Arguments must be valid JSON
            json.loads(tc["function"]["arguments"])

        _log_contract_result(
            provider="opencodego",
            model="deepseek-v4-flash",
            elapsed_ms=elapsed,
            status="success",
            detail=f"tool_calls={has_tool_calls} content={has_content}",
        )

    @pytest.mark.asyncio
    async def test_ask_with_tools_shape(self, ds_client) -> None:
        """High-level ``ask_with_tools`` returns a complete response."""
        start = time.monotonic()
        result = await ds_client.ask_with_tools(
            system_prompt="You are a helpful cost estimator.",
            user_message="What's the total cost for project 42?",
        )
        elapsed = (time.monotonic() - start) * 1000

        assert "choices" in result
        assert "usage" in result
        msg = result["choices"][0].get("message", {})
        assert msg.get("content") is not None or "tool_calls" in msg

        _log_contract_result(
            provider="opencodego",
            model="deepseek-v4-flash",
            elapsed_ms=elapsed,
            status="success",
            detail="ask_with_tools",
        )
