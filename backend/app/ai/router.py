"""Unified AI router — all model calls go through here for cache, retry, timeout.

Provides lazy-initialised, circuit-breaker-wrapped access to the MiMo
vision client and DeepSeek text client.
"""

from __future__ import annotations

from app.ai.circuit_breaker import CircuitBreaker
from app.ai.deepseek_client import DeepSeekClient
from app.ai.mimo_client import MimoVisionClient
from app.ai.models import ModelCapability

# ---------------------------------------------------------------------------
# Module-level singletons (lazy)
# ---------------------------------------------------------------------------

_vision_client: MimoVisionClient | None = None
_text_client: DeepSeekClient | None = None
_breaker = CircuitBreaker()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_client(capability: str) -> MimoVisionClient | DeepSeekClient:
    """Get the appropriate client for a capability, with circuit breaker.

    Parameters
    ----------
    capability:
        One of ``"vision"``, ``"text"``.

    Returns
    -------
    MimoVisionClient | DeepSeekClient
        The lazy-initialised client instance.

    Raises
    ------
    ValueError
        For an unknown capability string.
    """
    if capability == ModelCapability.VISION.value:
        global _vision_client
        if _vision_client is None:
            _vision_client = MimoVisionClient(circuit_breaker=_breaker)
        return _vision_client
    elif capability == ModelCapability.TEXT.value:
        global _text_client
        if _text_client is None:
            _text_client = DeepSeekClient(circuit_breaker=_breaker)
        return _text_client
    raise ValueError(
        f"Unknown capability: {capability!r}. "
        f"Expected one of: {[m.value for m in ModelCapability]}"
    )


def reset_clients() -> None:
    """Reset all cached client instances (useful for tests)."""
    global _vision_client, _text_client
    _vision_client = None
    _text_client = None
    _breaker.reset()


def circuit_breaker() -> CircuitBreaker:
    """Return the shared circuit breaker instance."""
    return _breaker
