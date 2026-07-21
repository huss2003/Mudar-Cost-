"""Model registry — centralised model specs for all AI providers.

Every model used by the system is declared here with its capabilities,
pricing, and constraints.  Consumers reference models by registry key
instead of inlining string literals.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModelCapability(Enum):
    VISION = "vision"
    TEXT = "text"
    EMBEDDING = "embedding"


@dataclass(frozen=True)
class ModelSpec:
    """Immutable specification for an AI model."""

    name: str
    provider: str
    capability: ModelCapability
    max_tokens: int
    cost_per_1k_input: float
    cost_per_1k_output: float
    supports_tools: bool = False
    supports_vision: bool = False


# ---------------------------------------------------------------------------
# Registry — all known models live here
# ---------------------------------------------------------------------------

MODELS: dict[str, ModelSpec] = {
    "mimo-v2.5": ModelSpec(
        name="mimo-v2.5",
        provider="opencodego",
        capability=ModelCapability.VISION,
        max_tokens=128000,
        cost_per_1k_input=0.0005,
        cost_per_1k_output=0.0015,
        supports_vision=True,
    ),
    "deepseek-v4-flash": ModelSpec(
        name="deepseek-v4-flash",
        provider="opencodego",
        capability=ModelCapability.TEXT,
        max_tokens=128000,
        cost_per_1k_input=0.0005,
        cost_per_1k_output=0.0015,
        supports_tools=True,
    ),
}


def get_model(key: str) -> ModelSpec:
    """Look up a model by registry key.

    Raises ``ValueError`` when *key* is unknown — the caller should
    catch this at startup / configuration time, never at request time.
    """
    if key not in MODELS:
        raise ValueError(
            f"Unknown model: {key!r}. "
            f"Available: {sorted(MODELS)}"
        )
    return MODELS[key]
