"""DeepSeek V4 Flash API client with tool/function calling support.

Features
--------
- Circuit breaker, structured logging (structlog), retry, and model registry.
- OpenAI-compatible tool/function calling format.
- Mock mode gated on ``mock=True`` OR ``ENVIRONMENT="development"``.
- **Production safety**: raises ``ValueError`` at construction when the
  API key is missing and the environment is **not** development.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.ai.circuit_breaker import CircuitBreaker
from app.ai.models import ModelSpec, get_model, ModelCapability
from app.config import settings
from app.services.metrics import ai_calls, mock_mode_fallback
from app.services.trace import get_trace_id

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions available to the features agent
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_project_boq",
            "description": "Get the full BOQ for a project, optionally filtered by trade",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "trade": {
                        "type": "string",
                        "description": "Optional trade filter",
                    },
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_material_alternatives",
            "description": "Find cheaper or alternative materials for BOQ items",
            "parameters": {
                "type": "object",
                "properties": {
                    "boq_item_id": {"type": "integer"},
                    "max_price_pct": {
                        "type": "number",
                        "description": (
                            "Max price as % of current "
                            "(e.g. 80 means up to 20% cheaper)"
                        ),
                    },
                },
                "required": ["boq_item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_history",
            "description": "Get past project history for comparison",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "limit": {
                        "type": "integer",
                        "description": "Number of similar projects",
                    },
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_productivity_rates",
            "description": "Get productivity rates by trade for duration estimation",
            "parameters": {
                "type": "object",
                "properties": {
                    "trades": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["trades"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class DeepSeekConfig:
    """Configuration for the DeepSeek V4 Flash API client."""

    api_key: str = ""  # Set explicitly or auto-resolved from env
    endpoint: str = "https://api.xiaomimimo.com/v1/chat/completions"
    model_key: str = "mimo-v2.5"
    max_retries: int = 3
    timeout_seconds: int = 120
    cost_per_1k_input: float = 0.0005  # USD estimate
    cost_per_1k_output: float = 0.0015  # USD estimate
    mock_mode: bool = False


# ---------------------------------------------------------------------------
# Mock response templates
# ---------------------------------------------------------------------------

_MOCK_CONTENT_RESPONSE: dict[str, Any] = {
    "choices": [
        {
            "message": {
                "content": (
                    "This is a mock response. The project BOQ shows "
                    "a total estimated cost of $125,000 across all trades."
                ),
            },
        },
    ],
    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
}

_MOCK_TOOL_CALL_RESPONSE: dict[str, Any] = {
    "choices": [
        {
            "message": {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_mock_001",
                        "type": "function",
                        "function": {
                            "name": "get_project_boq",
                            "arguments": json.dumps({"project_id": 42}),
                        },
                    },
                    {
                        "id": "call_mock_002",
                        "type": "function",
                        "function": {
                            "name": "get_material_alternatives",
                            "arguments": json.dumps(
                                {"boq_item_id": 101, "max_price_pct": 80}
                            ),
                        },
                    },
                ],
            },
        },
    ],
    "usage": {"prompt_tokens": 150, "completion_tokens": 80},
}


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------


class DeepSeekClient:
    """Client for the DeepSeek V4 Flash chat-completion API.

    Parameters
    ----------
    config:
        Optional :class:`DeepSeekConfig`.  When *None* defaults are used.
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
        config: DeepSeekConfig | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.config = config or DeepSeekConfig()
        self._breaker = circuit_breaker or CircuitBreaker()

        # Resolve API key from explicit config → env
        api_key = self.config.api_key or settings.DEEPSEEK_API_KEY or ""
        self.config.api_key = api_key

        # Resolve mock mode
        is_dev = settings.ENVIRONMENT in ("dev", "development")
        if self.config.mock_mode:
            pass  # explicitly asked for mock
        elif is_dev and not api_key:
            self.config.mock_mode = True
            logger.info("DeepSeek mock mode auto-enabled (dev environment, no key)")
            mock_mode_fallback.labels(
                provider="deepseek",
                model=self.config.model_key,
            ).inc()
        elif not is_dev and not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is not set and ENVIRONMENT is not 'development'. "
                "Cannot run in production without an API key."
            )

        # Validate model
        try:
            self._spec: ModelSpec = get_model(self.config.model_key)
        except ValueError:
            self._spec = ModelSpec(
                name=self.config.model_key,
                provider="unknown",
                capability=ModelCapability.TEXT,
                max_tokens=128000,
                cost_per_1k_input=self.config.cost_per_1k_input,
                cost_per_1k_output=self.config.cost_per_1k_output,
                supports_tools=True,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ask(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Send a chat completion request to DeepSeek V4 Flash.

        Parameters
        ----------
        messages:
            OpenAI-format message list.
        tools:
            Optional list of tool definitions (OpenAI function-calling format).
        temperature:
            Sampling temperature (default 0.3).

        Returns
        -------
        dict
            Parsed response containing ``content``, ``tool_calls``,
            and ``usage`` keys.
        """
        if self.config.mock_mode:
            return self._mock_ask(tools)

        return await self._breaker.call_async(
            self._real_ask,
            messages,
            tools,
            temperature,
        )

    async def ask_with_tools(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """High-level wrapper: builds messages array, calls **ask()**.

        Parameters
        ----------
        system_prompt:
            System-level instruction.
        user_message:
            The user's question or request.
        tools:
            Optional list of tool definitions.  Defaults to the built-in
            :data:`TOOLS` list if *None*.

        Returns
        -------
        dict
            The full response from **ask()** (may include tool_calls).
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return await self.ask(messages, tools=tools or TOOLS)

    # ------------------------------------------------------------------
    # Mock mode
    # ------------------------------------------------------------------

    def _mock_ask(self, tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Return a canned response without calling the API."""
        if tools:
            response = _MOCK_TOOL_CALL_RESPONSE
        else:
            response = _MOCK_CONTENT_RESPONSE

        time.sleep(0.05)

        usage = response["usage"]
        prompt_tokens = usage.get("prompt_tokens", 0) or 0
        completion_tokens = usage.get("completion_tokens", 0) or 0

        logger.info(
            "ai_call",
            model=self.config.model_key,
            latency_ms=50,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=round(
                (prompt_tokens * self._spec.cost_per_1k_input
                 + completion_tokens * self._spec.cost_per_1k_output) / 1000.0,
                6,
            ),
            status="mock",
            has_tools=tools is not None,
            trace_id=get_trace_id(),
        )

        ai_calls.labels(
            provider="deepseek",
            model=self.config.model_key,
            outcome="mock",
        ).inc()

        return response

    # ------------------------------------------------------------------
    # Real API call
    # ------------------------------------------------------------------

    async def _real_ask(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Execute the chat-completion API call with retry."""
        start = time.monotonic()
        last_error: str | None = None
        total_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}
        call_count = 0

        body: dict[str, Any] = {
            "model": self.config.model_key,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 8192,
        }
        if tools:
            body["tools"] = tools

        for attempt in range(1, self.config.max_retries + 1):
            call_count = attempt
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self.config.timeout_seconds)
                ) as client:
                    resp = await client.post(
                        self.config.endpoint,
                        headers={
                            "api-key": self.config.api_key,
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                    resp.raise_for_status()
                    data: dict[str, Any] = resp.json()

                usage = data.get("usage", {})
                total_usage = {
                    "prompt_tokens": usage.get("prompt_tokens", 0) or 0,
                    "completion_tokens": usage.get("completion_tokens", 0) or 0,
                }

                prompt_tokens = total_usage["prompt_tokens"]
                completion_tokens = total_usage["completion_tokens"]
                latency_ms = (time.monotonic() - start) * 1000
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
                    trace_id=get_trace_id(),
                )

                ai_calls.labels(
                    provider="deepseek",
                    model=self.config.model_key,
                    outcome="success",
                ).inc()

                return data

            except httpx.TimeoutException:
                last_error = f"Request timed out after {self.config.timeout_seconds}s"
                logger.warning(
                    "DeepSeek attempt %d/%d timed out",
                    attempt,
                    self.config.max_retries,
                )
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else "?"
                body_text = (
                    exc.response.text[:500] if exc.response is not None else ""
                )
                last_error = f"HTTP {status}: {body_text}"
                logger.warning(
                    "DeepSeek attempt %d/%d HTTP error: %s",
                    attempt,
                    self.config.max_retries,
                    last_error,
                )
            except (httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                last_error = f"Connection error: {exc}"
                logger.warning(
                    "DeepSeek attempt %d/%d connection error: %s",
                    attempt,
                    self.config.max_retries,
                    exc,
                )
            except httpx.RequestError as exc:
                last_error = f"Request failed: {exc}"
                logger.warning(
                    "DeepSeek attempt %d/%d request error: %s",
                    attempt,
                    self.config.max_retries,
                    exc,
                )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                last_error = f"Response parse error: {exc}"
                logger.warning(
                    "DeepSeek attempt %d/%d parse error: %s",
                    attempt,
                    self.config.max_retries,
                    exc,
                )
            except Exception as exc:
                last_error = f"Unexpected error: {exc}"
                logger.warning(
                    "DeepSeek attempt %d/%d unexpected error: %s",
                    attempt,
                    self.config.max_retries,
                    exc,
                )

            if attempt < self.config.max_retries:
                delay = 2 ** (attempt - 1)
                logger.info("Retrying in %ds ...", delay)
                await asyncio.sleep(delay)

        # All retries exhausted
        latency_ms = (time.monotonic() - start) * 1000
        logger.error(
            "ai_call",
            model=self.config.model_key,
            latency_ms=round(latency_ms, 1),
            prompt_tokens=total_usage["prompt_tokens"],
            completion_tokens=total_usage["completion_tokens"],
            cost_usd=0.0,
            status="failed",
            error=last_error,
            trace_id=get_trace_id(),
        )

        ai_calls.labels(
            provider="deepseek",
            model=self.config.model_key,
            outcome="failed",
        ).inc()
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            f"API call failed after "
                            f"{self.config.max_retries} retries: {last_error}"
                        ),
                    },
                },
            ],
            "usage": total_usage,
            "error": last_error,
        }
