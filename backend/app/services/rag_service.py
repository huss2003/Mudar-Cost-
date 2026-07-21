"""RAG (Retrieval-Augmented Generation) service for project/BOQ context.

Provides functions to index projects and BOQ items with embeddings, find
similar projects/items via pgvector cosine similarity, and perform general-
purpose RAG searches.
"""

import random
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.embedder import (
    EmbeddingConfig,
    build_project_context_text,
    embed_texts,
)
from app.config import settings
from app.models.core import Project
from app.models.detection import BOQItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_MODE: bool = not bool(settings.DEEPSEEK_API_KEY)


def _mock_similar(limit: int) -> list[dict]:
    """Return fake similar-project results for mock mode."""
    names = [
        "Commercial Tower A",
        "Residential Complex B",
        "Mall Renovation C",
        "Hospital Wing D",
        "School Building E",
    ]
    return [
        {
            "id": 100 + i,
            "name": names[i % len(names)],
            "similarity_score": round(random.uniform(0.75, 0.98), 4),
            "grand_total": random.uniform(500_000, 5_000_000),
        }
        for i in range(limit)
    ]


def _mock_boq_items(limit: int) -> list[dict]:
    """Return fake similar-BOQ-item results for mock mode."""
    descs = [
        "Vitrified tile flooring 600x600 mm",
        "Gypsum board false ceiling",
        "Acrylic emulsion paint for walls",
        "Concrete block masonry 200mm thick",
        "MS angle iron framework",
    ]
    return [
        {
            "id": 200 + i,
            "description": descs[i % len(descs)],
            "project_id": 100 + i,
            "category": "finishing",
            "similarity_score": round(random.uniform(0.70, 0.95), 4),
            "total": random.uniform(10_000, 500_000),
            "unit": "sqm",
        }
        for i in range(limit)
    ]


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

async def index_project(
    db: AsyncSession,
    project_id: int,
    config: Optional[EmbeddingConfig] = None,
) -> bool:
    """Embed a project and all its BOQ items, then store vectors in the DB.

    Returns *True* on success, *False* if the project was not found.
    """
    # 1. Load project + BOQ items + materials eagerly
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.boq_items),
        )
    )
    result = await db.execute(stmt)
    project: Optional[Project] = result.scalar_one_or_none()
    if project is None:
        return False

    boq_items = list(project.boq_items)

    # 2. Build project-level context text
    project_dict = {
        "name": project.name,
        "client": project.client or "",
        "location": project.location or "",
        "status": project.status,
        "grand_total": project.grand_total or 0,
    }

    boq_dicts = []
    for item in boq_items:
        boq_dicts.append({
            "description": item.description,
            "material_name": item.material_name or "",
        })

    context_text = build_project_context_text(project_dict, boq_dicts)

    # 3. Generate embedding for the project
    vectors = await embed_texts([context_text], config=config)
    project_embedding = vectors[0]

    # 4. Store on Project model
    project.embedding = project_embedding

    # 5. Index individual BOQ items (generate embeddings from their descriptions)
    if boq_items:
        descriptions = [
            (
                f"{item.description} — {item.category or ''} — "
                f"{item.material_name or ''}"
            )
            for item in boq_items
        ]
        item_vectors = await embed_texts(descriptions, config=config)

        for item, vec in zip(boq_items, item_vectors):
            item.embedding = vec

    await db.flush()
    return True


# ---------------------------------------------------------------------------
# Similarity search
# ---------------------------------------------------------------------------

async def find_similar_projects(
    db: AsyncSession,
    project_id: int,
    limit: int = 5,
    config: Optional[EmbeddingConfig] = None,
) -> list[dict]:
    """Find projects similar to the given project via cosine similarity.

    Returns a list of ``{id, name, similarity_score, grand_total}`` dicts
    sorted by descending similarity (most similar first).
    """
    if _MOCK_MODE:
        return _mock_similar(limit)

    # 1. Get the query project's embedding
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project: Optional[Project] = result.scalar_one_or_none()

    if project is None or project.embedding is None:
        return []

    query_vec = project.embedding

    # 2. Nearest neighbors via pgvector cosine distance (<=>)
    #    cos_distance = 1 - cosine_similarity
    #    We ORDER BY distance ASC (closest first), then convert to similarity.
    embedding_col = Project.embedding
    distance_expr = embedding_col.op("<=>")(query_vec)

    search_stmt = (
        select(
            Project.id,
            Project.name,
            distance_expr.label("distance"),
            Project.grand_total,
        )
        .where(Project.id != project_id)
        .where(Project.embedding.isnot(None))
        .order_by(distance_expr)
        .limit(limit)
    )

    rows = await db.execute(search_stmt)
    results = []
    for row in rows:
        similarity = max(0.0, 1.0 - float(row.distance))
        results.append({
            "id": row.id,
            "name": row.name,
            "similarity_score": round(similarity, 4),
            "grand_total": row.grand_total or 0,
        })

    return results


async def find_similar_boq_items(
    db: AsyncSession,
    description: str,
    limit: int = 5,
    config: Optional[EmbeddingConfig] = None,
) -> list[dict]:
    """Find BOQ items whose description is semantically similar to *description*.

    Returns a list of ``{id, description, project_id, category,
    similarity_score, total, unit}`` dicts.
    """
    if _MOCK_MODE:
        return _mock_boq_items(limit)

    # 1. Embed the query description
    vectors = await embed_texts([description], config=config)
    query_vec = vectors[0]

    # 2. Search via pgvector cosine distance
    embedding_col = BOQItem.embedding
    distance_expr = embedding_col.op("<=>")(query_vec)

    search_stmt = (
        select(
            BOQItem.id,
            BOQItem.description,
            BOQItem.project_id,
            BOQItem.category,
            distance_expr.label("distance"),
            BOQItem.total,
            BOQItem.unit,
        )
        .where(BOQItem.embedding.isnot(None))
        .order_by(distance_expr)
        .limit(limit)
    )

    rows = await db.execute(search_stmt)
    results = []
    for row in rows:
        similarity = max(0.0, 1.0 - float(row.distance))
        results.append({
            "id": row.id,
            "description": row.description,
            "project_id": row.project_id,
            "category": row.category or "",
            "similarity_score": round(similarity, 4),
            "total": row.total or 0,
            "unit": row.unit,
        })

    return results


# ---------------------------------------------------------------------------
# General-purpose RAG search
# ---------------------------------------------------------------------------

async def rag_search(
    db: AsyncSession,
    query: str,
    project_id: Optional[int] = None,
    limit: int = 5,
    config: Optional[EmbeddingConfig] = None,
) -> list[dict]:
    """General-purpose RAG search across projects and BOQ items.

    1. Embed *query*.
    2. Search both ``projects`` and ``boq_items`` tables via pgvector cosine
       similarity.
    3. If *project_id* is given, only return results from that project.
    4. Return a combined list of context snippets with similarity scores.

    Each result dict contains:
    ``type`` ("project" | "boq_item"), ``id``, ``text`` (snippet),
    ``similarity_score``, and type-specific metadata.
    """
    if _MOCK_MODE:
        mock_projects = _mock_similar(limit // 2 + 1)
        mock_items = _mock_boq_items(limit // 2 + 1)
        combined: list[dict] = []
        for p in mock_projects:
            combined.append({
                "type": "project",
                "id": p["id"],
                "text": p["name"],
                "similarity_score": p["similarity_score"],
                "grand_total": p["grand_total"],
            })
        for i in mock_items:
            combined.append({
                "type": "boq_item",
                "id": i["id"],
                "text": i["description"],
                "similarity_score": i["similarity_score"],
                "project_id": i["project_id"],
                "category": i["category"],
                "total": i["total"],
                "unit": i["unit"],
            })
        combined.sort(key=lambda x: x["similarity_score"], reverse=True)
        return combined[:limit]

    # 1. Embed query
    vectors = await embed_texts([query], config=config)
    query_vec = vectors[0]

    results: list[dict] = []

    # --- Search projects ---
    proj_distance = Project.embedding.op("<=>")(query_vec)
    proj_stmt = (
        select(
            Project.id,
            Project.name,
            proj_distance.label("distance"),
            Project.grand_total,
        )
        .where(Project.embedding.isnot(None))
        .order_by(proj_distance)
        .limit(limit)
    )

    if project_id is not None:
        proj_stmt = proj_stmt.where(Project.id == project_id)

    proj_rows = await db.execute(proj_stmt)
    for row in proj_rows:
        similarity = max(0.0, 1.0 - float(row.distance))
        results.append({
            "type": "project",
            "id": row.id,
            "text": row.name,
            "similarity_score": round(similarity, 4),
            "grand_total": row.grand_total or 0,
        })

    # --- Search BOQ items ---
    item_distance = BOQItem.embedding.op("<=>")(query_vec)
    item_stmt = (
        select(
            BOQItem.id,
            BOQItem.description,
            BOQItem.project_id,
            BOQItem.category,
            item_distance.label("distance"),
            BOQItem.total,
            BOQItem.unit,
        )
        .where(BOQItem.embedding.isnot(None))
        .order_by(item_distance)
        .limit(limit)
    )

    if project_id is not None:
        item_stmt = item_stmt.where(BOQItem.project_id == project_id)

    item_rows = await db.execute(item_stmt)
    for row in item_rows:
        similarity = max(0.0, 1.0 - float(row.distance))
        results.append({
            "type": "boq_item",
            "id": row.id,
            "text": row.description,
            "similarity_score": round(similarity, 4),
            "project_id": row.project_id,
            "category": row.category or "",
            "total": row.total or 0,
            "unit": row.unit,
        })

    # Sort by similarity descending
    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    return results[:limit]
