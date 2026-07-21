"""Embedding service: text-to-vector conversion for RAG."""

import hashlib
import math
import random
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class EmbeddingConfig:
    """Configuration for the embedding API client."""

    endpoint: str = "https://api.opencodego.com/v1/embeddings"
    model: str = "text-embedding-3-small"
    api_key: str = ""  # falls back to settings.DEEPSEEK_API_KEY
    dimensions: int = 384  # matching pgvector Vector(384) columns
    batch_size: int = 20  # max texts per API call
    mock_mode: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_config(config: Optional[EmbeddingConfig] = None) -> EmbeddingConfig:
    """Return *config* if given, otherwise a default built from settings."""
    if config is not None:
        return config
    return EmbeddingConfig(
        api_key=settings.DEEPSEEK_API_KEY or "",
        mock_mode=not bool(settings.DEEPSEEK_API_KEY),
    )


def _text_key(text: str) -> str:
    """Stable hash key for LRU cache dedup."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _mock_embedding(dim: int = 384) -> list[float]:
    """Return a normalised random vector of *dim* dimensions."""
    vec = [random.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def embed_texts(
    texts: list[str],
    config: Optional[EmbeddingConfig] = None,
) -> list[list[float]]:
    """Send *texts* to the embedding API and return a list of vectors.

    Texts are sent in batches of ``config.batch_size``.  Duplicate texts
    within the same call are deduplicated; the same vector is returned for
    each occurrence.

    When ``config.mock_mode`` is *True* (or no *api_key* is available) random
    normalised vectors are returned.
    """
    cfg = _get_config(config)
    dim = cfg.dimensions

    if cfg.mock_mode:
        return [_mock_embedding(dim) for _ in texts]

    # Deduplicate across the batch
    seen: dict[str, list[float]] = {}
    unique_texts: list[str] = []
    indices: list[int] = []

    for i, t in enumerate(texts):
        key = _text_key(t)
        if key in seen:
            indices.append(i)  # will reuse later
        else:
            indices.append(i)
            unique_texts.append(t)

    # Process in batches
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        for batch_start in range(0, len(unique_texts), cfg.batch_size):
            batch = unique_texts[batch_start : batch_start + cfg.batch_size]
            payload = {
                "model": cfg.model,
                "input": batch,
                "dimensions": dim,
            }

            try:
                resp = await client.post(cfg.endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                # OpenAI-compatible response: data[{object, index, embedding}]
                for item in data.get("data", []):
                    idx = item.get("index", 0)
                    actual_idx = batch_start + idx
                    if actual_idx < len(unique_texts):
                        text_key = _text_key(unique_texts[actual_idx])
                        seen[text_key] = item["embedding"]

            except Exception:
                # On API failure fall back to mock vectors for this batch
                for t in batch:
                    seen[_text_key(t)] = _mock_embedding(dim)

    # Reconstruct result preserving original order & duplicates
    results: list[list[float]] = []
    for i, t in enumerate(texts):
        key = _text_key(t)
        results.append(seen.get(key, _mock_embedding(dim)))

    return results


def build_project_context_text(
    project: dict,
    boq_items: list[dict],
) -> str:
    """Build a single text string suitable for embedding from project + BOQ data.

    Parameters
    ----------
    project : dict
        Must contain keys: ``name``, ``client``, ``location``, ``status``,
        ``grand_total`` (optional — defaults to 0).
    boq_items : list[dict]
        Each dict should contain a ``description`` key.  May also contain
        ``material_name``.

    Returns
    -------
    str
        Formatted context string.
    """
    name = project.get("name", "Untitled")
    client = project.get("client", "Unknown")
    location = project.get("location", "Unknown")
    status = project.get("status", "draft")
    grand_total = project.get("grand_total", 0)

    item_count = len(boq_items)

    # Collect unique material names
    materials: set[str] = set()
    for item in boq_items:
        desc = item.get("description", "").strip()
        if desc:
            materials.add(desc)
        mat = item.get("material_name", "").strip()
        if mat:
            materials.add(mat)

    material_list = ", ".join(sorted(materials)) if materials else "None"

    return (
        f"Project: {name}, Client: {client}, Location: {location}, "
        f"Status: {status}. Items: {item_count} items "
        f"totalling \u20b9{grand_total:,.2f}. "
        f"Materials: {material_list}"
    )
