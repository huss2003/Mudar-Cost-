"""AI / vision API client package for MiMo v2.5 and DeepSeek V4 Flash integration.

Embedding & RAG services for pgvector-powered semantic search.
"""

from app.ai.circuit_breaker import CircuitBreaker
from app.ai.deepseek_client import DeepSeekClient, DeepSeekConfig, TOOLS
from app.ai.mimo_client import MimoVisionClient, MimoConfig
from app.ai.models import ModelSpec, ModelCapability, MODELS, get_model
from app.ai.router import get_client, reset_clients, circuit_breaker
from app.ai.embedder import (
    EmbeddingConfig,
    build_project_context_text,
    embed_texts,
)

__all__ = [
    "CircuitBreaker",
    "DeepSeekClient",
    "DeepSeekConfig",
    "EmbeddingConfig",
    "MimoConfig",
    "MimoVisionClient",
    "ModelCapability",
    "ModelSpec",
    "MODELS",
    "TOOLS",
    "build_project_context_text",
    "circuit_breaker",
    "embed_texts",
    "get_client",
    "get_model",
    "reset_clients",
]
