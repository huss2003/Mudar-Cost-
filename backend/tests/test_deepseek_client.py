"""Unit tests for the DeepSeek V4 Flash API client wrapper.

Test classes:
- TestMockMode: mock detection returns content, mock tool call returns tool_calls
- TestCostLogging: verify cost calculation matches expected
- TestConfig: empty key triggers mock (in dev), real key keeps real mode
"""

from __future__ import annotations

import json
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import httpx
import pytest

from app.ai.deepseek_client import (
    TOOLS,
    DeepSeekClient,
    DeepSeekConfig,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client() -> DeepSeekClient:
    """Client configured for explicit mock mode (no real API calls)."""
    return DeepSeekClient(DeepSeekConfig(mock_mode=True))


@pytest.fixture
def empty_key_dev_client(monkeypatch: pytest.MonkeyPatch) -> DeepSeekClient:
    """Client with empty API key in dev mode → auto mock mode."""
    monkeypatch.setattr("app.config.settings.DEEPSEEK_API_KEY", "")
    return DeepSeekClient(DeepSeekConfig(api_key=""))


# ---------------------------------------------------------------------------
# Mock-mode tests
# ---------------------------------------------------------------------------


class TestMockMode:
    """Verify mock-mode behaviour without any API dependency."""

    @pytest.mark.asyncio
    async def test_mock_ask_returns_content(self, mock_client: DeepSeekClient) -> None:
        """Mock ask() returns a content response when no tools provided."""
        result = await mock_client.ask(
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert isinstance(result, dict)
        assert "choices" in result
        assert result["choices"][0]["message"]["content"] is not None
        assert "mock" in result["choices"][0]["message"]["content"].lower()

    @pytest.mark.asyncio
    async def test_mock_ask_with_tools_returns_calls(
        self, mock_client: DeepSeekClient
    ) -> None:
        """Mock ask() returns tool_calls when tools are provided."""
        result = await mock_client.ask(
            messages=[{"role": "user", "content": "Find BOQ data"}],
            tools=TOOLS,
        )
        assert isinstance(result, dict)
        msg = result["choices"][0]["message"]
        assert msg["content"] is None
        assert "tool_calls" in msg
        assert len(msg["tool_calls"]) > 0
        call = msg["tool_calls"][0]
        assert call["type"] == "function"
        assert call["function"]["name"] == "get_project_boq"

    @pytest.mark.asyncio
    async def test_mock_ask_with_tools_result_structure(
        self, mock_client: DeepSeekClient
    ) -> None:
        """Mock tool call response has all expected fields."""
        result = await mock_client.ask(
            messages=[{"role": "user", "content": "Analyze project"}],
            tools=TOOLS,
        )
        msg = result["choices"][0]["message"]
        calls = msg["tool_calls"]
        assert len(calls) == 2

        assert calls[0]["id"] == "call_mock_001"
        assert calls[0]["function"]["name"] == "get_project_boq"
        args = json.loads(calls[0]["function"]["arguments"])
        assert args["project_id"] == 42

        assert calls[1]["function"]["name"] == "get_material_alternatives"
        args2 = json.loads(calls[1]["function"]["arguments"])
        assert args2["boq_item_id"] == 101
        assert args2["max_price_pct"] == 80

    @pytest.mark.asyncio
    async def test_mock_usage_in_response(self, mock_client: DeepSeekClient) -> None:
        """Mock response has usage stats."""
        result = await mock_client.ask(
            messages=[{"role": "user", "content": "Hello"}],
        )
        usage = result.get("usage", {})
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 50

    @pytest.mark.asyncio
    async def test_mock_usage_with_tools(self, mock_client: DeepSeekClient) -> None:
        """Mock tool call response has correct usage stats."""
        result = await mock_client.ask(
            messages=[{"role": "user", "content": "Use tools"}],
            tools=TOOLS,
        )
        usage = result.get("usage", {})
        assert usage["prompt_tokens"] == 150
        assert usage["completion_tokens"] == 80

    @pytest.mark.asyncio
    async def test_mock_ask_with_tools_high_level(
        self, mock_client: DeepSeekClient
    ) -> None:
        """ask_with_tools in mock mode returns tool_calls."""
        result = await mock_client.ask_with_tools(
            system_prompt="You are a cost estimator",
            user_message="Analyze project 42",
            tools=TOOLS,
        )
        msg = result["choices"][0]["message"]
        assert msg["content"] is None
        assert "tool_calls" in msg
        assert len(msg["tool_calls"]) == 2

    @pytest.mark.asyncio
    async def test_mock_ask_without_tools_high_level(
        self, mock_client: DeepSeekClient
    ) -> None:
        """ask_with_tools defaults to TOOLS when tools=None, returns tool_calls."""
        result = await mock_client.ask_with_tools(
            system_prompt="You are a cost estimator",
            user_message="Say hello",
            tools=None,
        )
        msg = result["choices"][0]["message"]
        assert msg["content"] is None
        assert "tool_calls" in msg


# ---------------------------------------------------------------------------
# Cost logging tests
# ---------------------------------------------------------------------------


class TestCostLogging:
    """Verify cost calculation and logging."""

    @pytest.mark.asyncio
    async def test_cost_calculation_mock(self, mock_client: DeepSeekClient) -> None:
        """Mock mode cost calculation is correct (input + output)."""
        result = await mock_client.ask(
            messages=[{"role": "user", "content": "Hi"}],
        )
        usage = result["usage"]
        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]

        cfg = mock_client.config
        expected_input_cost = (prompt_tokens * cfg.cost_per_1k_input) / 1000.0
        expected_output_cost = (completion_tokens * cfg.cost_per_1k_output) / 1000.0
        expected_total = expected_input_cost + expected_output_cost

        assert expected_input_cost == 100 * 0.0005 / 1000 == 0.00005
        assert expected_output_cost == 50 * 0.0015 / 1000 == 0.000075
        assert expected_total == 0.000125

    @pytest.mark.asyncio
    async def test_cost_calculation_mock_with_tools(
        self, mock_client: DeepSeekClient
    ) -> None:
        """Mock tool call cost calculation is correct."""
        result = await mock_client.ask(
            messages=[{"role": "user", "content": "Use tools"}],
            tools=TOOLS,
        )
        usage = result["usage"]
        cfg = mock_client.config
        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]

        expected_input_cost = (prompt_tokens * cfg.cost_per_1k_input) / 1000.0
        expected_output_cost = (completion_tokens * cfg.cost_per_1k_output) / 1000.0

        assert expected_input_cost == 150 * 0.0005 / 1000 == 0.000075
        assert abs(expected_output_cost - 80 * 0.0015 / 1000) < 1e-12

    @pytest.mark.asyncio
    async def test_log_cost_with_structlog(
        self, mock_client: DeepSeekClient
    ) -> None:
        """Mock ask() logs structured ai_call event."""
        with patch("app.ai.deepseek_client.logger.info") as mock_log:
            await mock_client.ask(
                messages=[{"role": "user", "content": "Hello"}],
            )

            mock_log.assert_called_once()
            args = mock_log.call_args
            assert args[0][0] == "ai_call" or len(args[0]) > 0
            kwargs = args[1]
            assert kwargs.get("model") == "mimo-v2.5"
            assert kwargs.get("status") == "mock"
            assert kwargs.get("prompt_tokens", 0) > 0
            assert kwargs.get("cost_usd") is not None

    def test_log_cost_edge_cases(self, mock_client: DeepSeekClient) -> None:
        """_mock_ask handles zero tokens gracefully."""
        # With no tools → content response (prompt_tokens=100, completion_tokens=50)
        with patch("app.ai.deepseek_client.logger.info") as mock_log:
            mock_client._mock_ask(tools=None)
            mock_log.assert_called_once()
            args = mock_log.call_args
            kwargs = args[1]
            assert kwargs.get("prompt_tokens") == 100
            assert kwargs.get("completion_tokens") == 50

    def test_log_cost_empty_dict(self, mock_client: DeepSeekClient) -> None:
        """_mock_ask handles missing usage gracefully."""
        with patch("app.ai.deepseek_client.logger.info") as mock_log:
            # Mock the _MOCK_CONTENT_RESPONSE to have empty usage
            import app.ai.deepseek_client as ds_mod
            original = ds_mod._MOCK_CONTENT_RESPONSE.copy()
            ds_mod._MOCK_CONTENT_RESPONSE = {
                "choices": [{"message": {"content": "test"}}],
                "usage": {},
            }
            try:
                mock_client._mock_ask(tools=None)
                mock_log.assert_called_once()
                kwargs = mock_log.call_args[1]
                assert kwargs.get("prompt_tokens") == 0
                assert kwargs.get("completion_tokens") == 0
                assert kwargs.get("cost_usd") == 0.0
            finally:
                ds_mod._MOCK_CONTENT_RESPONSE = original

    def test_log_cost_none_values(self, mock_client: DeepSeekClient) -> None:
        """_mock_ask handles None token values safely."""
        with patch("app.ai.deepseek_client.logger.info") as mock_log:
            import app.ai.deepseek_client as ds_mod
            original = ds_mod._MOCK_CONTENT_RESPONSE.copy()
            ds_mod._MOCK_CONTENT_RESPONSE = {
                "choices": [{"message": {"content": "test"}}],
                "usage": {"prompt_tokens": None, "completion_tokens": None},
            }
            try:
                mock_client._mock_ask(tools=None)
                mock_log.assert_called_once()
                kwargs = mock_log.call_args[1]
                assert kwargs.get("prompt_tokens") == 0
                assert kwargs.get("completion_tokens") == 0
            finally:
                ds_mod._MOCK_CONTENT_RESPONSE = original


# ---------------------------------------------------------------------------
# Config / auto-detection tests
# ---------------------------------------------------------------------------


class TestConfig:
    """Client auto-detects mock mode from empty API keys in dev environment."""

    def test_empty_key_triggers_mock_in_dev(
        self, empty_key_dev_client: DeepSeekClient
    ) -> None:
        """Empty API key + dev env sets mock_mode to True."""
        assert empty_key_dev_client.config.mock_mode is True
        assert empty_key_dev_client.config.api_key == ""

    def test_real_key_keeps_real_mode(self) -> None:
        """A real-looking key does NOT trigger mock mode."""
        client = DeepSeekClient(DeepSeekConfig(api_key="sk-12345"))
        assert client.config.mock_mode is False
        assert client.config.api_key == "sk-12345"

    def test_explicit_mock_flag(self) -> None:
        """Explicit mock_mode=True always enables mock, even with a key."""
        client = DeepSeekClient(DeepSeekConfig(api_key="sk-12345", mock_mode=True))
        assert client.config.mock_mode is True

    def test_default_config(self) -> None:
        """Default DeepSeekConfig has expected values."""
        config = DeepSeekConfig()
        assert config.api_key == ""
        assert config.endpoint == "https://api.xiaomimimo.com/v1/chat/completions"
        assert config.model_key == "mimo-v2.5"
        assert config.max_retries == 3
        assert config.timeout_seconds == 120
        assert config.cost_per_1k_input == 0.0005
        assert config.cost_per_1k_output == 0.0015
        assert config.mock_mode is False

    def test_custom_config(self) -> None:
        """Custom config overrides every default."""
        config = DeepSeekConfig(
            api_key="custom-key",
            endpoint="https://custom.endpoint/v1/chat",
            model_key="deepseek-v4",
            max_retries=5,
            timeout_seconds=300,
            cost_per_1k_input=0.001,
            cost_per_1k_output=0.003,
            mock_mode=True,
        )
        assert config.api_key == "custom-key"
        assert config.endpoint == "https://custom.endpoint/v1/chat"
        assert config.model_key == "deepseek-v4"
        assert config.max_retries == 5
        assert config.timeout_seconds == 300
        assert config.cost_per_1k_input == 0.001
        assert config.cost_per_1k_output == 0.003
        assert config.mock_mode is True


# ---------------------------------------------------------------------------
# Production guard tests
# ---------------------------------------------------------------------------


class TestProductionGuard:
    """Production environment raises ValueError when keys are missing."""

    def test_production_no_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """In production, missing API key raises ValueError."""
        monkeypatch.setattr("app.config.settings.ENVIRONMENT", "production")
        monkeypatch.setattr("app.config.settings.DEEPSEEK_API_KEY", "")
        with pytest.raises(ValueError, match="DEEPSEEK_API_KEY is not set"):
            DeepSeekClient(DeepSeekConfig(api_key=""))

    def test_production_with_key_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """In production, a valid API key works fine."""
        monkeypatch.setattr("app.config.settings.ENVIRONMENT", "production")
        client = DeepSeekClient(DeepSeekConfig(api_key="sk-real-key"))
        assert client.config.mock_mode is False
        assert client.config.api_key == "sk-real-key"


# ---------------------------------------------------------------------------
# TOOLS definitions tests (unchanged)
# ---------------------------------------------------------------------------


class TestToolsDefinitions:
    """Verify the built-in TOOLS list matches expected structure."""

    def test_tools_is_list(self) -> None:
        assert isinstance(TOOLS, list)
        assert len(TOOLS) >= 1

    def test_tools_have_required_fields(self) -> None:
        for tool in TOOLS:
            assert tool["type"] == "function"
            assert "function" in tool
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            assert "type" in func["parameters"]
            assert func["parameters"]["type"] == "object"

    def test_tool_names(self) -> None:
        names = {t["function"]["name"] for t in TOOLS}
        assert "get_project_boq" in names
        assert "get_material_alternatives" in names
        assert "get_project_history" in names
        assert "get_productivity_rates" in names


# ---------------------------------------------------------------------------
# Real-mode error handling tests (async, using httpx patching)
# ---------------------------------------------------------------------------


class TestRealModeErrors:
    """Real mode gracefully handles network errors."""

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self) -> None:
        """Client retries on httpx.TimeoutException."""
        client = DeepSeekClient(DeepSeekConfig(api_key="sk-test-key", max_retries=2))

        with patch("app.ai.deepseek_client.httpx.AsyncClient") as mock_http:
            mock_instance = AsyncMock()
            mock_http.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.side_effect = __import__(
                "httpx"
            ).TimeoutException("timeout", request=MagicMock())

            result = await client.ask(
                messages=[{"role": "user", "content": "Hello"}],
            )

            assert result.get("error") is not None
            assert "failed after" in result["choices"][0]["message"]["content"]
            assert mock_instance.post.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_http_error(self) -> None:
        """Client retries on HTTP 5xx errors."""
        client = DeepSeekClient(DeepSeekConfig(api_key="sk-test-key", max_retries=2))

        with patch("app.ai.deepseek_client.httpx.AsyncClient") as mock_http:
            mock_instance = AsyncMock()
            mock_http.return_value.__aenter__.return_value = mock_instance

            mock_response = MagicMock()
            mock_response.status_code = 502
            mock_response.text = "Bad Gateway"
            mock_response.raise_for_status.side_effect = (
                httpx.HTTPStatusError(
                    "502",
                    request=MagicMock(),
                    response=mock_response,
                )
            )
            mock_instance.post.return_value = mock_response

            result = await client.ask(
                messages=[{"role": "user", "content": "Hello"}],
            )

            assert result.get("error") is not None
            assert "HTTP 502" in result["error"]
            assert mock_instance.post.call_count == 2

    @pytest.mark.asyncio
    async def test_successful_real_call(self) -> None:
        """Successful API call returns parsed response."""
        client = DeepSeekClient(DeepSeekConfig(api_key="sk-test-key", max_retries=1))

        response_data = {
            "choices": [
                {
                    "message": {
                        "content": "The total project cost is $125,000.",
                    },
                },
            ],
            "usage": {"prompt_tokens": 80, "completion_tokens": 30},
        }

        with patch("app.ai.deepseek_client.httpx.AsyncClient") as mock_http:
            mock_instance = AsyncMock()
            mock_http.return_value.__aenter__.return_value = mock_instance

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = response_data
            mock_instance.post.return_value = mock_response

            result = await client.ask(
                messages=[{"role": "user", "content": "Hello"}],
            )

            assert result["choices"][0]["message"]["content"] == (
                "The total project cost is $125,000."
            )
            assert result["usage"]["prompt_tokens"] == 80
            assert result["usage"]["completion_tokens"] == 30

    @pytest.mark.asyncio
    async def test_successful_with_tool_call(self) -> None:
        """Successful API call with tool calling returns tool_calls."""
        client = DeepSeekClient(DeepSeekConfig(api_key="sk-test-key", max_retries=1))

        response_data = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_abc123",
                                "type": "function",
                                "function": {
                                    "name": "get_project_boq",
                                    "arguments": json.dumps(
                                        {"project_id": 42, "trade": "finish"}
                                    ),
                                },
                            },
                        ],
                    },
                },
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 45},
        }

        with patch("app.ai.deepseek_client.httpx.AsyncClient") as mock_http:
            mock_instance = AsyncMock()
            mock_http.return_value.__aenter__.return_value = mock_instance

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = response_data
            mock_instance.post.return_value = mock_response

            result = await client.ask(
                messages=[{"role": "user", "content": "Get project BOQ"}],
                tools=TOOLS,
            )

            msg = result["choices"][0]["message"]
            assert msg["content"] is None
            assert len(msg["tool_calls"]) == 1
            assert msg["tool_calls"][0]["function"]["name"] == "get_project_boq"
            args = json.loads(msg["tool_calls"][0]["function"]["arguments"])
            assert args["project_id"] == 42

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        """Client returns error envelope on connection failure."""
        client = DeepSeekClient(DeepSeekConfig(api_key="sk-test-key", max_retries=1))

        with patch("app.ai.deepseek_client.httpx.AsyncClient") as mock_http:
            mock_instance = AsyncMock()
            mock_http.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.side_effect = httpx.ConnectError(
                "connection refused", request=MagicMock()
            )

            result = await client.ask(
                messages=[{"role": "user", "content": "Hello"}],
            )

            assert result.get("error") is not None
            assert "connection refused" in result["error"].lower()
