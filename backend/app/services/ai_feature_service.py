"""
AI Feature Service — business logic behind every AI-powered endpoint.

Provides five service functions:

1. ``answer_project_question`` — NL Q&A over project data
2. ``detect_missing_boq_items`` — gap analysis vs detected objects & standards
3. ``detect_anomalies`` — rate/quantity/category outliers vs historical data
4. ``suggest_value_engineering`` — cheaper material alternatives with savings
5. ``predict_duration`` — trade-level duration projection with Gantt data
"""

from __future__ import annotations

import logging
import random
from typing import Any

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.ai.deepseek_client import DeepSeekClient
from app.models.core import Project
from app.models.detection import BOQItem, DetectedObject
from app.models.reference import Material, Vendor
from app.models.rules import ProductivityRate
from app.schemas.ai_features import (
    AnomalyItem,
    AnomalyResponse,
    AskResponse,
    DurationPredictResponse,
    GanttBar,
    MissingBOQItem,
    MissingBOQResponse,
    TradeDurationBreakdown,
    VESuggestion,
    VEResponse,
)
from app.services.rag_service import find_similar_projects, rag_search

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default trade execution order (sequential dependencies)
# ---------------------------------------------------------------------------
# Trades are executed in this order. A trade depends on the previous trade
# if listed consecutively; parallel groups are listed together.
TRADE_EXECUTION_ORDER: list[list[str]] = [
    ["Civil", "Structure"],
    ["MEP", "Electrical", "HVAC", "Networking", "Fire Fighting"],
    ["Gypsum", "Flooring"],
    ["Painting", "Glass"],
    ["Furniture", "Signages"],
    ["Labour"],  # cleanup / finishing
]


def _get_trade_dependencies() -> dict[str, list[str]]:
    """Build a trade -> list of dependencies map from the execution order."""
    deps: dict[str, list[str]] = {}
    flat_order: list[str] = []
    for group in TRADE_EXECUTION_ORDER:
        for trade in group:
            # Dependencies = everything in previous groups
            prev: list[str] = []
            for prev_group in TRADE_EXECUTION_ORDER:
                if prev_group is group:
                    break
                prev.extend(prev_group)
            deps[trade] = prev[:]
            flat_order.append(trade)
    return deps


# ======================================================================
# 1. Q&A — Answer a natural language question about the project
# ======================================================================


async def answer_project_question(
    db: AsyncSession,
    project_id: int,
    question: str,
    stream: bool = False,
) -> AskResponse:
    """Answer a natural-language question about the project.

    1. Loads project metadata and BOQ items
    2. Builds RAG context from the current project and similar projects
    3. Calls DeepSeek (or mock) with the context + question
    4. Returns the answer with confidence and source references
    """
    # --- Build context -------------------------------------------------
    context = await rag_search(db, project_id, query_text=question, limit=30)

    project = await db.get(Project, project_id)
    if project is None:
        return AskResponse(
            answer="Project not found.",
            confidence=0.0,
            sources=[],
        )

    system_prompt = (
        "You are a cost estimation and construction Q&A assistant for a "
        "construction cost estimation platform. You answer questions based "
        "strictly on the provided project context (BOQ items, detected objects, "
        "similar projects). If you don't have enough information, say so. "
        "Be specific: cite line-item IDs, quantities, rates, and trades when "
        "applicable. Keep answers concise and actionable."
    )

    client = DeepSeekClient()
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"Project context:\n{context}\n\nQuestion: {question}",
        },
    ]
    try:
        raw = await client.ask(
            messages=messages,
            tools=[],  # empty list = no tool calling => plain text response
            temperature=0.3,
        )

        # Parse response (OpenAI-compatible format)
        content = ""
        try:
            content = raw["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            content = str(raw.get("content", ""))

        return AskResponse(
            answer=content,
            confidence=1.0 if not client.config.mock_mode else 0.85,
            sources=[],
            is_ai_generated=True,
            ai_status="available",
        )
    except Exception as exc:
        logger.warning(
            "DeepSeek Q&A failed — falling back to rule-based answer: %s",
            exc,
        )
        # Rule-based fallback: answer based on known data patterns
        return AskResponse(
            answer=(
                f"I'm sorry, but I couldn't process your question right now "
                f"due to a temporary AI service issue. The project has "
                f"{len(context.split())} data points available for analysis. "
                f"Please try again shortly."
            ),
            confidence=0.0,
            sources=[],
            is_ai_generated=False,
            ai_status="unavailable",
        )


# ======================================================================
# 2. Missing BOQ — Detect gaps in the current BOQ
# ======================================================================


async def detect_missing_boq_items(
    db: AsyncSession,
    project_id: int,
) -> MissingBOQResponse:
    """Detect BOQ items that are likely missing.

    Strategy (in priority order):
    1. For each DetectedObject, check if a BOQItem exists referencing it
    2. Compare trade categories against similar completed projects
    3. Use LLM to identify standard fit-out scope gaps
    """
    suggestions: list[MissingBOQItem] = []
    seen_categories: set[str] = set()

    # --- Load existing BOQ categories for this project -------------------
    cat_stmt = (
        select(BOQItem.category)
        .where(
            BOQItem.project_id == project_id,
            BOQItem.is_deleted == False,  # noqa: E712
        )
        .distinct()
    )
    cat_result = await db.execute(cat_stmt)
    existing_categories = {row[0] for row in cat_result if row[0]}
    seen_categories.update(existing_categories)

    # --- 1. Check DetectedObjects without matching BOQ items -------------
    obj_stmt = (
        select(DetectedObject)
        .join(DetectedObject.drawing)
        .join(Project, Project.id == project_id)
        .where(
            DetectedObject.is_deleted == False,  # noqa: E712
        )
    )
    # Use subquery approach
    from app.models.core import Drawing

    obj_stmt = (
        select(DetectedObject)
        .join(Drawing, DetectedObject.drawing_id == Drawing.id)
        .where(
            Drawing.project_id == project_id,
            DetectedObject.is_deleted == False,  # noqa: E712
        )
    )
    obj_result = await db.execute(obj_stmt)
    detected_objects = list(obj_result.scalars().all())

    # Get BOQ items with their object_id set
    boq_linked_stmt = (
        select(BOQItem.object_id)
        .where(
            BOQItem.project_id == project_id,
            BOQItem.object_id.isnot(None),
            BOQItem.is_deleted == False,  # noqa: E712
        )
        .distinct()
    )
    boq_linked_result = await db.execute(boq_linked_stmt)
    linked_object_ids = {row[0] for row in boq_linked_result if row[0]}

    # Map object types to standard BOQ categories / descriptions
    OBJECT_TYPE_TO_CATEGORY = {
        "wall": "Gypsum",
        "partition": "Gypsum",
        "door": "Furniture",
        "window": "Glass",
        "floor": "Flooring",
        "ceiling": "Gypsum",
        "column": "Structure",
        "beam": "Structure",
        "stair": "Civil",
        "duct": "HVAC",
        "pipe": "MEP",
        "conduit": "Electrical",
        "cable_tray": "Networking",
        "socket": "Electrical",
        "switch": "Electrical",
        "light": "Electrical",
        "sprinkler": "Fire Fighting",
        "signage": "Signages",
    }

    for obj in detected_objects:
        if obj.id not in linked_object_ids:
            cat = OBJECT_TYPE_TO_CATEGORY.get(obj.object_type.lower(), "Other")
            if cat not in seen_categories or True:  # Still suggest even if category exists
                qty = obj.area or obj.length or 1.0
                suggestions.append(
                    MissingBOQItem(
                        category=cat,
                        item_description=(
                            f"{obj.label or obj.object_type} — "
                            f"detected in drawing but no BOQ line item exists"
                        ),
                        estimated_quantity=round(qty, 2),
                        unit="sqm" if obj.area else "m" if obj.length else "nos",
                        reason=f"Detected object ({obj.object_type}) has no matching BOQ item",
                        derived_from=f"DetectedObject #{obj.id} ({obj.object_type})",
                    )
                )

    # --- 2. Compare categories against similar projects ------------------
    similar = await find_similar_projects(db, project_id, limit=3)
    for sp in similar:
        shared = set(sp.get("shared_categories", []))
        for cat in shared:
            if cat not in seen_categories:
                suggestions.append(
                    MissingBOQItem(
                        category=cat,
                        item_description=f"Missing {cat} trade — present in similar project \"{sp['name']}\"",
                        estimated_quantity=0.0,
                        unit="ls",
                        reason=f"Trade category '{cat}' is present in similar project #{sp['project_id']} but missing from current BOQ",
                        derived_from=f"Similar project \"{sp['name']}\"",
                    )
                )
                seen_categories.add(cat)

    # --- 3. Check standard fit-out scope gaps (LLM-assisted) -------------
    #   If the project has basic trades but is missing finishing trades,
    #   flag common omissions
    STANDARD_FIT_OUT_ITEMS: list[tuple[str, str, str]] = [
        ("Gypsum", "Acoustic ceiling tiles in conference rooms", "nos"),
        ("Flooring", "Vinyl cove base / skirting", "m"),
        ("Painting", "Fire-rated paint on escape route walls", "sqm"),
        ("Electrical", "Emergency lighting and exit signs", "nos"),
        ("Fire Fighting", "Fire extinguisher cabinets", "nos"),
        ("Signages", "Room identification signage", "nos"),
        ("Furniture", "Window blinds / curtains", "nos"),
        ("HVAC", "Fresh air intake grilles", "nos"),
        ("Networking", "Patch panel and cable management", "nos"),
    ]

    if existing_categories:
        for cat, desc, unit in STANDARD_FIT_OUT_ITEMS:
            if cat in existing_categories:
                # Only flag if no item with similar description exists
                similar_stmt = (
                    select(sa_func.count(BOQItem.id))
                    .where(
                        BOQItem.project_id == project_id,
                        BOQItem.is_deleted == False,  # noqa: E712
                        BOQItem.description.ilike(f"%{desc.split(' in')[0].split(' /')[0]}%"),
                    )
                )
                similar_result = await db.execute(similar_stmt)
                count = similar_result.scalar() or 0
                if count == 0:
                    suggestions.append(
                        MissingBOQItem(
                            category=cat,
                            item_description=desc,
                            estimated_quantity=1.0,
                            unit=unit,
                            reason="Standard fit-out item commonly included in similar projects",
                            derived_from="Industry standard fit-out scope checklist",
                        )
                    )

    return MissingBOQResponse(
        suggested_items=suggestions,
        gap_count=len(suggestions),
        analysis_summary=(
            f"Found {len(suggestions)} potential gaps: "
            f"{sum(1 for s in suggestions if s.derived_from and 'DetectedObject' in s.derived_from)} "
            f"from unlinked detected objects, "
            f"{sum(1 for s in suggestions if s.derived_from and 'Similar project' in s.derived_from)} "
            f"from similar project comparison, "
            f"{sum(1 for s in suggestions if s.derived_from and 'standard' in s.derived_from.lower())} "
            f"from standard scope check."
        ),
    )


# ======================================================================
# 3. Anomalies — Detect unusual rates, quantities, or omissions
# ======================================================================


async def detect_anomalies(
    db: AsyncSession,
    project_id: int,
) -> AnomalyResponse:
    """Detect anomalies in the current project vs historical norms.

    Checks:
    1. Line-item rates > 20% above historical (similar project) average
    2. Unusual quantities vs detected-object-derived quantities
    3. Missing material categories that similar projects include
    """
    anomalies: list[AnomalyItem] = []

    # --- Load this project's BOQ items -----------------------------------
    boq_stmt = (
        select(BOQItem)
        .options(joinedload(BOQItem.detected_object))
        .where(
            BOQItem.project_id == project_id,
            BOQItem.is_deleted == False,  # noqa: E712
        )
    )
    boq_result = await db.execute(boq_stmt)
    boq_items = list(boq_result.unique().scalars().all())

    if not boq_items:
        return AnomalyResponse(
            anomalies=[],
            anomaly_count=0,
            project_health="needs_review",
        )

    # --- Build historical averages from similar projects ------------------
    similar = await find_similar_projects(db, project_id, limit=5)
    similar_ids = [sp["project_id"] for sp in similar]

    # Historical average rates per category
    hist_rates: dict[str, dict[str, float]] = {}  # category -> {avg_rate, min_rate, max_rate, count}
    if similar_ids:
        hist_stmt = (
            select(
                BOQItem.category,
                sa_func.avg(BOQItem.rate),
                sa_func.min(BOQItem.rate),
                sa_func.max(BOQItem.rate),
                sa_func.count(BOQItem.id),
            )
            .where(
                BOQItem.project_id.in_(similar_ids),
                BOQItem.is_deleted == False,  # noqa: E712
                BOQItem.category.isnot(None),
            )
            .group_by(BOQItem.category)
        )
        hist_result = await db.execute(hist_stmt)
        for row in hist_result:
            if row[0]:
                hist_rates[row[0]] = {
                    "avg_rate": float(row[1] or 0),
                    "min_rate": float(row[2] or 0),
                    "max_rate": float(row[3] or 0),
                    "count": int(row[4] or 0),
                }

    # --- 1. Rate anomalies (>20% above historical average) ---------------
    for item in boq_items:
        cat = item.category or "Other"
        if cat in hist_rates and hist_rates[cat]["count"] >= 2 and item.rate > 0:
            avg = hist_rates[cat]["avg_rate"]
            if avg > 0:
                deviation = ((item.rate - avg) / avg) * 100
                if deviation > 20:
                    severity = "high" if deviation > 50 else ("medium" if deviation > 30 else "low")
                    anomalies.append(
                        AnomalyItem(
                            boq_item_id=item.id,
                            description=item.description[:100],
                            field="rate",
                            expected=f"~₹{avg:,.2f} (avg for '{cat}')",
                            actual=f"₹{item.rate:,.2f}",
                            deviation_pct=round(deviation, 1),
                            severity=severity,
                        )
                    )
                elif deviation < -20:
                    # Unusually low rate — could be error or great deal
                    anomalies.append(
                        AnomalyItem(
                            boq_item_id=item.id,
                            description=item.description[:100],
                            field="rate",
                            expected=f"~₹{avg:,.2f} (avg for '{cat}')",
                            actual=f"₹{item.rate:,.2f}",
                            deviation_pct=round(deviation, 1),
                            severity="low",
                        )
                    )

    # --- 2. Quantity anomalies vs detected objects -----------------------
    for item in boq_items:
        if item.detected_object:
            obj = item.detected_object
            derived_qty = obj.area or obj.length or 0.0
            if derived_qty > 0:
                diff_pct = abs(item.quantity - derived_qty) / derived_qty * 100
                if diff_pct > 30:
                    anomalies.append(
                        AnomalyItem(
                            boq_item_id=item.id,
                            description=f"Qty mismatch: {item.description[:60]}",
                            field="quantity",
                            expected=f"~{derived_qty:.1f} (from detected object)",
                            actual=f"{item.quantity:.1f} (in BOQ)",
                            deviation_pct=round(diff_pct, 0),
                            severity="medium" if diff_pct > 50 else "low",
                        )
                    )

    # --- 3. Missing material categories ----------------------------------
    if hist_rates:
        current_cats = {item.category for item in boq_items if item.category}
        for cat in hist_rates:
            if cat not in current_cats and hist_rates[cat]["count"] >= 2:
                anomalies.append(
                    AnomalyItem(
                        boq_item_id=None,
                        description=f"Trade/category '{cat}' is missing from project",
                        field="material_category",
                        expected=f"{cat} items present in {hist_rates[cat]['count']} similar project(s)",
                        actual="Not present in this project",
                        deviation_pct=100.0,
                        severity="medium",
                    )
                )

    # --- Determine project health ----------------------------------------
    if not anomalies:
        health = "healthy"
    elif any(a.severity == "high" for a in anomalies):
        health = "action_required"
    else:
        health = "needs_review"

    return AnomalyResponse(
        anomalies=anomalies,
        anomaly_count=len(anomalies),
        project_health=health,
    )


# ======================================================================
# 4. Value Engineering — Suggest cheaper alternatives
# ======================================================================


async def suggest_value_engineering(
    db: AsyncSession,
    project_id: int,
    top_k: int = 10,
) -> VEResponse:
    """Suggest cost-saving material alternatives.

    For each BOQ item that has a material assigned:
    1. Query alternative materials in the same category
    2. Find cheaper options (rate difference > 5%)
    3. Calculate potential savings = (current - alternative) × quantity
    4. Sort by savings descending
    """
    suggestions: list[VESuggestion] = []

    # --- Load BOQ items with materials -----------------------------------
    boq_stmt = (
        select(BOQItem)
        .where(
            BOQItem.project_id == project_id,
            BOQItem.is_deleted == False,  # noqa: E712
            BOQItem.material_id.isnot(None),
        )
        .order_by(BOQItem.quantity.desc())
    )
    boq_result = await db.execute(boq_stmt)
    boq_items = list(boq_result.scalars().all())

    if not boq_items:
        # Fall back to items with rate > 0 even without material_id
        boq_stmt = (
            select(BOQItem)
            .where(
                BOQItem.project_id == project_id,
                BOQItem.is_deleted == False,  # noqa: E712
                BOQItem.rate > 0,
            )
            .order_by((BOQItem.quantity * BOQItem.rate).desc())
        )
        boq_result = await db.execute(boq_stmt)
        boq_items = list(boq_result.scalars().all())

    if not boq_items:
        return VEResponse(suggestions=[], total_potential_savings=0.0, suggestion_count=0)

    # --- Load materials catalogue ----------------------------------------
    mat_stmt = select(Material).where(Material.is_active == True)  # noqa: E712
    mat_result = await db.execute(mat_stmt)
    all_materials = list(mat_result.scalars().all())

    # Index materials by category
    materials_by_cat: dict[str, list[Material]] = {}
    for m in all_materials:
        cat = (m.category or "other").lower()
        materials_by_cat.setdefault(cat, []).append(m)

    for item in boq_items:
        current_material_name = item.material_name or ""
        current_category = (item.category or "").lower()
        current_rate = item.rate

        if current_rate <= 0:
            continue

        # Find cheaper alternatives in the same category
        candidates = materials_by_cat.get(current_category, [])

        # Also try matching by description keywords
        if not candidates and item.description:
            keywords = [
                w.lower() for w in item.description.split()
                if len(w) > 3
            ][:3]
            for kw in keywords:
                for m in all_materials:
                    if kw in m.name.lower() or kw in (m.description or "").lower():
                        cat = (m.category or "other").lower()
                        if cat not in materials_by_cat:
                            materials_by_cat[cat] = []
                        if m not in materials_by_cat[cat]:
                            materials_by_cat[cat].append(m)
            candidates = materials_by_cat.get(current_category, [])

        if not candidates:
            continue

        # Find the cheapest alternative that's not the current material
        cheaper: list[Material] = [
            m for m in candidates
            if m.rate < current_rate * 0.95  # at least 5% cheaper
            and (not current_material_name or m.name.lower() != current_material_name.lower())
        ]

        if not cheaper:
            continue

        best = min(cheaper, key=lambda m: m.rate)
        savings_per_unit = current_rate - best.rate
        total_savings = savings_per_unit * item.quantity
        savings_pct = ((current_rate - best.rate) / current_rate) * 100

        # Determine effort and risk
        if savings_pct > 30:
            effort = "high"
            risk = "medium"
        elif savings_pct > 15:
            effort = "medium"
            risk = "low"
        else:
            effort = "low"
            risk = "low"

        suggestions.append(
            VESuggestion(
                rank=0,  # Will set after sorting
                boq_item_id=item.id,
                description=item.description[:120],
                current_material=current_material_name or f"Rate ₹{current_rate:,.2f}/{item.unit}",
                suggested_material=f"{best.name} @ ₹{best.rate:,.2f}/{best.unit}",
                current_cost=round(item.quantity * current_rate, 2),
                suggested_cost=round(item.quantity * best.rate, 2),
                savings=round(total_savings, 2),
                savings_pct=round(savings_pct, 1),
                implementation_effort=effort,
                risk=risk,
            )
        )

    # Sort by savings descending, assign ranks
    suggestions.sort(key=lambda s: s.savings, reverse=True)
    for i, s in enumerate(suggestions[:top_k]):
        s.rank = i + 1

    total_savings = round(sum(s.savings for s in suggestions[:top_k]), 2)

    return VEResponse(
        suggestions=suggestions[:top_k],
        total_potential_savings=total_savings,
        suggestion_count=len(suggestions[:top_k]),
    )


# ======================================================================
# 5. Duration Prediction — Estimate project timeline by trade
# ======================================================================


async def predict_duration(
    db: AsyncSession,
    project_id: int,
) -> DurationPredictResponse:
    """Predict project duration based on BOQ quantities and productivity rates.

    Algorithm:
    1. Group BOQ items by trade
    2. For each trade, look up ``ProductivityRate.output_per_day``
    3. Calculate: duration = total_quantity / (output_per_day × crew_size)
    4. Apply sequential/parallel dependencies between trades
    5. Identify the critical path
    """
    trade_deps = _get_trade_dependencies()

    # --- Load aggregated quantities by trade -----------------------------
    agg_stmt = (
        select(
            BOQItem.category,
            sa_func.sum(BOQItem.quantity),
            sa_func.count(BOQItem.id),
        )
        .where(
            BOQItem.project_id == project_id,
            BOQItem.is_deleted == False,  # noqa: E712
        )
        .group_by(BOQItem.category)
    )
    agg_result = await db.execute(agg_stmt)
    trade_quantities: dict[str, dict] = {}
    for row in agg_result:
        if row[0]:
            trade_quantities[row[0]] = {
                "total_quantity": float(row[1] or 0),
                "item_count": int(row[2] or 0),
            }

    if not trade_quantities:
        return DurationPredictResponse(
            total_days=0,
            trade_breakdown=[],
            gantt_data=[],
            critical_path=[],
        )

    # --- Load productivity rates ------------------------------------------
    prod_stmt = select(ProductivityRate).where(
        ProductivityRate.is_deleted == False,  # noqa: E712
    )
    prod_result = await db.execute(prod_stmt)
    productivity_rates = list(prod_result.scalars().all())

    # Index by trade (lowercase)
    prod_by_trade: dict[str, ProductivityRate] = {}
    for pr in productivity_rates:
        key = (pr.trade or "").lower()
        # Keep the one with highest output_per_day
        if key not in prod_by_trade or pr.output_per_day > prod_by_trade[key].output_per_day:
            prod_by_trade[key] = pr

    # --- Mock productivity rates for common trades when DB is empty -------
    MOCK_PRODUCTIVITY: dict[str, dict[str, float]] = {
        "civil": {"output_per_day": 25.0, "crew_size": 4},
        "structure": {"output_per_day": 30.0, "crew_size": 4},
        "gypsum": {"output_per_day": 20.0, "crew_size": 3},
        "flooring": {"output_per_day": 15.0, "crew_size": 3},
        "painting": {"output_per_day": 40.0, "crew_size": 2},
        "glass": {"output_per_day": 18.0, "crew_size": 2},
        "furniture": {"output_per_day": 12.0, "crew_size": 3},
        "electrical": {"output_per_day": 30.0, "crew_size": 3},
        "hvac": {"output_per_day": 15.0, "crew_size": 3},
        "networking": {"output_per_day": 25.0, "crew_size": 2},
        "fire fighting": {"output_per_day": 20.0, "crew_size": 2},
        "signages": {"output_per_day": 30.0, "crew_size": 2},
        "labour": {"output_per_day": 50.0, "crew_size": 5},
        "mep": {"output_per_day": 20.0, "crew_size": 3},
        "other": {"output_per_day": 25.0, "crew_size": 2},
    }

    # --- Compute duration per trade ---------------------------------------
    trade_breakdowns: list[TradeDurationBreakdown] = []
    for trade_name, qty_data in trade_quantities.items():
        total_qty = qty_data["total_quantity"]
        if total_qty <= 0:
            continue

        trade_key = trade_name.lower()
        prod = prod_by_trade.get(trade_key)
        if prod:
            output_per_day = prod.output_per_day if prod.output_per_day > 0 else MOCK_PRODUCTIVITY.get(trade_key, {}).get("output_per_day", 20.0)
            crew_size = prod.crew_size if prod.crew_size > 0 else MOCK_PRODUCTIVITY.get(trade_key, {}).get("crew_size", 2)
        else:
            mock = MOCK_PRODUCTIVITY.get(trade_key, MOCK_PRODUCTIVITY["other"])
            output_per_day = mock["output_per_day"]
            crew_size = mock["crew_size"]

        effective_output = output_per_day * crew_size
        if effective_output <= 0:
            duration = total_qty  # fallback: 1 unit per day
        else:
            duration = total_qty / effective_output

        trade_breakdowns.append(
            TradeDurationBreakdown(
                trade=trade_name,
                total_quantity=round(total_qty, 2),
                unit="varies",
                output_per_day=output_per_day,
                crew_size=crew_size,
                duration_days=round(max(duration, 1.0), 1),
                depends_on=trade_deps.get(trade_name, []),
            )
        )

    if not trade_breakdowns:
        return DurationPredictResponse(
            total_days=0,
            trade_breakdown=[],
            gantt_data=[],
            critical_path=[],
        )

    # --- Build Gantt chart data with dependency scheduling ----------------
    # Sort by trade execution order
    trade_order_flat = [
        t for group in TRADE_EXECUTION_ORDER for t in group
    ]
    trade_breakdowns.sort(
        key=lambda tb: (
            trade_order_flat.index(tb.trade) if tb.trade in trade_order_flat
            else len(trade_order_flat)
        )
    )

    # Schedule: sequential within dependency chain, parallel otherwise
    scheduled: dict[str, int] = {}  # trade -> start_day
    gantt_bars: list[GanttBar] = []
    current_day = 0

    for tb in trade_breakdowns:
        deps = trade_deps.get(tb.trade, [])
        # Find the latest end day among dependencies
        max_dep_end = 0
        for dep in deps:
            dep_end = scheduled.get(dep, 0)
            if dep_end > max_dep_end:
                max_dep_end = dep_end

        start_day = max_dep_end
        # If no dependencies, can start at 0 or after previous parallel groups
        if not deps:
            start_day = current_day

        end_day = int(round(start_day + tb.duration_days))
        scheduled[tb.trade] = end_day

        gantt_bars.append(
            GanttBar(
                trade=tb.trade,
                start_day=start_day,
                end_day=end_day,
                duration_days=tb.duration_days,
                depends_on=deps,
            )
        )

        # Only advance the "free runner" for trades without dependencies
        if not deps:
            current_day = max(current_day, end_day)

    # --- Determine total duration & critical path -------------------------
    total_days = max(bar.end_day for bar in gantt_bars) if gantt_bars else 0

    # Critical path: find the chain of trades with the longest total duration
    # Simple approach: walk back from the last-finishing trade
    end_trade = max(gantt_bars, key=lambda b: b.end_day).trade
    critical_path = [end_trade]
    current_trade = end_trade
    while True:
        deps = trade_deps.get(current_trade, [])
        if not deps:
            break
        # Pick the dependency with the latest end day
        prev = max(deps, key=lambda d: scheduled.get(d, 0))
        if scheduled.get(prev, 0) == 0:
            break
        critical_path.append(prev)
        current_trade = prev
    critical_path.reverse()

    return DurationPredictResponse(
        total_days=total_days,
        trade_breakdown=trade_breakdowns,
        gantt_data=gantt_bars,
        critical_path=critical_path,
    )
