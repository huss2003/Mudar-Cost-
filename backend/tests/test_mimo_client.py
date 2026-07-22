"""Unit tests for the MiMo v2.5 Vision API client wrapper."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest
from PIL import Image

from app.ai.mimo_client import MimoConfig, MimoVisionClient
from app.schemas.detection import DetectionResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client() -> MimoVisionClient:
    """Client configured for explicit mock mode (no real API calls)."""
    return MimoVisionClient(MimoConfig(mock_mode=True))


@pytest.fixture
def empty_key_dev_client(monkeypatch: pytest.MonkeyPatch) -> MimoVisionClient:
    """Client with empty API key in dev mode → auto mock mode."""
    monkeypatch.setattr("app.config.settings.MIMO_API_KEY", "")
    return MimoVisionClient(MimoConfig(api_key=""))


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Create a small valid PNG for real-mode testing."""
    img_path = tmp_path / "test.png"
    img = Image.new("RGB", (200, 100), color="white")
    img.save(img_path, format="PNG")
    return img_path


# ---------------------------------------------------------------------------
# Mock-mode tests (the primary tests specified in the task)
# ---------------------------------------------------------------------------


class TestMockDetection:
    """Verify mock-mode behaviour without any API dependency."""

    def test_mock_detection(self, mock_client: MimoVisionClient) -> None:
        """Mock mode returns a non-empty DetectionResult."""
        result = mock_client.detect_objects("nonexistent.png", prompt="test")
        assert isinstance(result, DetectionResult)
        assert len(result.objects) > 0
        assert result.objects[0].object_type in (
            "wall", "door", "window", "other",
        )

    def test_mock_object_schema(self, mock_client: MimoVisionClient) -> None:
        """Every mock object has required schema fields."""
        result = mock_client.detect_objects("nonexistent.png")
        assert len(result.objects) > 0
        obj = result.objects[0]
        assert obj.object_type is not None
        assert obj.confidence > 0
        assert obj.source == "ai"

    def test_mock_default_objects(self, mock_client: MimoVisionClient) -> None:
        """Default mock returns wall + door + window (3 objects)."""
        result = mock_client.detect_objects("nonexistent.png")
        types = {o.object_type for o in result.objects}
        assert "wall" in types
        assert "door" in types
        assert "window" in types
        assert len(result.objects) == 3

    def test_mock_with_room_prompt(self, mock_client: MimoVisionClient) -> None:
        """Room-related prompt adds a text-label object."""
        result = mock_client.detect_objects(
            "nonexistent.png", prompt="List all rooms"
        )
        types = {o.object_type for o in result.objects}
        assert "other" in types
        assert len(result.objects) == 4

    def test_mock_result_structure(self, mock_client: MimoVisionClient) -> None:
        """Mock DetectionResult carries expected metadata."""
        result = mock_client.detect_objects("nonexistent.png")
        assert result.status == "completed"
        assert result.source_format == "ai"
        assert result.drawing_id == 0
        assert result.errors == []


# ---------------------------------------------------------------------------
# Auto mock-mode detection tests (dev environment, no key)
# ---------------------------------------------------------------------------


class TestAutoMockMode:
    """Client auto-detects mock mode from empty API keys in dev environment."""

    def test_empty_key_triggers_mock_in_dev(
        self, empty_key_dev_client: MimoVisionClient
    ) -> None:
        """Empty API key + dev env → mock mode enabled."""
        assert empty_key_dev_client.config.mock_mode is True
        result = empty_key_dev_client.detect_objects("nope.png")
        assert len(result.objects) > 0

    def test_non_mock_key(self) -> None:
        """A real-looking key does NOT trigger mock mode."""
        client = MimoVisionClient(MimoConfig(api_key="sk-12345"))
        assert client.config.mock_mode is False

    def test_explicit_mock_flag(self) -> None:
        """Explicit mock_mode=True always enables mock, even with a key."""
        client = MimoVisionClient(MimoConfig(api_key="sk-12345", mock_mode=True))
        assert client.config.mock_mode is True


# ---------------------------------------------------------------------------
# Production guard tests
# ---------------------------------------------------------------------------


class TestProductionGuard:
    """Production environment raises ValueError when keys are missing."""

    def test_production_no_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """In production, missing API key raises ValueError."""
        monkeypatch.setattr("app.config.settings.ENVIRONMENT", "production")
        monkeypatch.setattr("app.config.settings.MIMO_API_KEY", "")
        with pytest.raises(ValueError, match="MIMO_API_KEY is not set"):
            MimoVisionClient(MimoConfig(api_key=""))

    def test_production_with_key_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """In production, a valid API key works fine."""
        monkeypatch.setattr("app.config.settings.ENVIRONMENT", "production")
        client = MimoVisionClient(MimoConfig(api_key="sk-real-key"))
        assert client.config.mock_mode is False
        assert client.config.api_key == "sk-real-key"


# ---------------------------------------------------------------------------
# Real-mode error handling tests
# ---------------------------------------------------------------------------


class TestRealModeErrors:
    """Real mode gracefully handles missing files and network errors."""

    def test_file_not_found(self) -> None:
        """Missing image returns a failed DetectionResult."""
        client = MimoVisionClient(MimoConfig(api_key="sk-test-key"))
        result = client.detect_objects("/nonexistent/path/foo.png")
        assert result.status == "failed"
        assert any("not found" in e.lower() for e in result.errors)

    def test_unreadable_file(self, tmp_path: Path) -> None:
        """Empty/corrupt file returns a failed DetectionResult."""
        bad = tmp_path / "bad.txt"
        bad.write_text("not an image")
        client = MimoVisionClient(MimoConfig(api_key="sk-test-key"))
        result = client.detect_objects(str(bad))
        assert result.status == "failed"
        assert len(result.errors) > 0

    @patch("app.ai.mimo_client.requests.post")
    def test_retry_on_failure(
        self, mock_post: MagicMock, sample_image: Path
    ) -> None:
        """Client retries on transient errors, then returns failed result."""
        mock_post.side_effect = ConnectionError("connection refused")

        config = MimoConfig(api_key="sk-test-key", max_retries=2)
        client = MimoVisionClient(config)
        result = client.detect_objects(str(sample_image))

        assert result.status == "failed"
        assert mock_post.call_count == 2  # max_retries

    @patch("app.ai.mimo_client.requests.post")
    def test_successful_real_call(
        self, mock_post: MagicMock, sample_image: Path
    ) -> None:
        """Successful API call returns completed result with parsed objects."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps([
                            {
                                "object_type": "wall",
                                "label": "Wall-A",
                                "bbox": [0.0, 0.0, 0.5, 0.2],
                                "confidence": 0.97,
                            },
                        ]),
                    }
                }
            ],
            "usage": {"total_tokens": 150, "prompt_tokens": 100, "completion_tokens": 50},
        }
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        config = MimoConfig(api_key="sk-test-key", max_retries=1)
        client = MimoVisionClient(config)
        result = client.detect_objects(str(sample_image))

        assert result.status == "completed"
        assert len(result.objects) == 1
        assert result.objects[0].object_type == "wall"
        assert result.objects[0].confidence == 0.97
        assert result.objects[0].source == "ai"


# ---------------------------------------------------------------------------
# JSON parsing tests (unchanged)
# ---------------------------------------------------------------------------


class TestJsonParsing:
    """_parse_objects_json handles various LLM response formats."""

    def test_direct_json_array(self) -> None:
        result = MimoVisionClient._parse_objects_json(
            '[{"object_type": "wall"}]'
        )
        assert len(result) == 1
        assert result[0]["object_type"] == "wall"

    def test_markdown_code_block(self) -> None:
        result = MimoVisionClient._parse_objects_json(
            '```json\n[{"object_type": "door"}]\n```'
        )
        assert len(result) == 1
        assert result[0]["object_type"] == "door"

    def test_wrapped_in_objects_key(self) -> None:
        result = MimoVisionClient._parse_objects_json(
            '{"objects": [{"object_type": "window"}]}'
        )
        assert len(result) == 1
        assert result[0]["object_type"] == "window"

    def test_empty_content(self) -> None:
        assert MimoVisionClient._parse_objects_json("") == []
        assert MimoVisionClient._parse_objects_json("  ") == []

    def test_malformed_content(self) -> None:
        assert MimoVisionClient._parse_objects_json("not json at all") == []


# ---------------------------------------------------------------------------
# Bbox conversion tests (unchanged)
# ---------------------------------------------------------------------------


class TestBboxConversion:
    """_fractional_to_mm converts properly."""

    def test_basic_conversion(self) -> None:
        config = MimoConfig(dpi=96, drawing_scale=100)
        client = MimoVisionClient(config)
        result = client._fractional_to_mm([0.0, 0.0, 0.5, 0.5], 200, 100)
        assert result is not None
        assert len(result) == 4
        expected_x = 0.5 * 200 * (25.4 / 96) * 100
        expected_y = 0.5 * 100 * (25.4 / 96) * 100
        assert abs(result[2] - expected_x) < 0.01
        assert abs(result[3] - expected_y) < 0.01

    def test_none_bbox(self) -> None:
        client = MimoVisionClient(MimoConfig())
        assert client._fractional_to_mm(None, 200, 100) is None

    def test_wrong_length(self) -> None:
        client = MimoVisionClient(MimoConfig())
        assert client._fractional_to_mm([0.1, 0.2], 200, 100) is None


# ---------------------------------------------------------------------------
# Image resize tests (unchanged)
# ---------------------------------------------------------------------------


class TestImageResize:
    """_resize_image keeps aspect ratio within max bounds."""

    def test_resize_down(self) -> None:
        img = Image.new("RGB", (2048, 1024))
        config = MimoConfig(max_image_size=(1024, 1024))
        client = MimoVisionClient(config)
        resized = client._resize_image(img)
        assert resized.width <= 1024
        assert resized.height <= 1024
        assert abs(resized.width / resized.height - 2.0) < 0.01

    def test_no_resize_needed(self) -> None:
        img = Image.new("RGB", (512, 512))
        config = MimoConfig(max_image_size=(1024, 1024))
        client = MimoVisionClient(config)
        resized = client._resize_image(img)
        assert resized.width == 512
        assert resized.height == 512


# ---------------------------------------------------------------------------
# Config tests (unchanged)
# ---------------------------------------------------------------------------


class TestMimoConfig:
    """MimoConfig dataclass defaults and construction."""

    def test_defaults(self) -> None:
        config = MimoConfig()
        assert config.endpoint == "https://api.xiaomimimo.com/v1/chat/completions"
        assert config.model_key == "mimo-v2.5"
        assert config.max_retries == 3
        assert config.timeout_seconds == 60
        assert config.rate_per_image == 0.003
        assert config.max_image_size == (1024, 1024)
        assert config.mock_mode is False
        assert config.dpi == 96.0
        assert config.drawing_scale == 100.0

    def test_custom_values(self) -> None:
        config = MimoConfig(
            api_key="custom-key",
            endpoint="https://custom.endpoint/v1/chat",
            model_key="mimo-v3",
            max_retries=5,
            timeout_seconds=120,
        )
        assert config.api_key == "custom-key"
        assert config.endpoint == "https://custom.endpoint/v1/chat"
        assert config.model_key == "mimo-v3"
        assert config.max_retries == 5
        assert config.timeout_seconds == 120
