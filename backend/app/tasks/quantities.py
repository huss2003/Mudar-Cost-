"""
Celery task for quantity computation via BOQ rule expansion.

Loads detected objects from analyzed drawings, expands them through the
dependency/rule engine (multi-level with cycle detection), writes BOQItem
rows, creates a CostVersion snapshot, and updates project status.

Uses structlog for structured JSON logging with trace_id propagation.
"""

from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any

import structlog
from sqlalchemy import func, select

from app.celery_app import DeadLetterTask, celery_app
from app.database import async_session
from app.models.core import Drawing, Project
from app.models.detection import BOQItem, CostVersion, DetectedObject
from app.models.rules import BOQRule
from app.services.dependency_engine import expand_with_dependencies
from app.services.metrics import boq_computed, objects_detected
from app.services.rule_engine import ExpandedLineItem
from app.services.trace import set_trace_id, get_trace_id

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Conversion helpers  —  SQLAlchemy → plain dicts for the rule engine
# ---------------------------------------------------------------------------


def _detected_to_dict(obj: DetectedObject) -> dict[str, Any]:
    """Convert a DetectedObject model to a plain dict for the rule engine."""
    return {
        "id": obj.id,
        "drawing_id": obj.drawing_id,
        "object_type": obj.object_type,
        "label": obj.label,
        "length": obj.length or 0.0,
        "width": obj.width or 0.0,
        "area": obj.area or 0.0,
        "height": obj.height or 0.0,
        "thickness": obj.thickness or 0.0,
        "layer": obj.layer,
    }


def _rule_to_dict(rule: BOQRule) -> dict[str, Any]:
    """Convert a BOQRule model to a plain dict for the rule engine."""
    d: dict[str, Any] = {
        "id": rule.id,
        "object_type": rule.object_type,
        "name": rule.name,
        "trade": rule.trade,
        "sub_items": rule.sub_items or [],
    }
    if rule.formula:
        d["formula"] = rule.formula
    if rule.description:
        d["description"] = rule.description
    if rule.version:
        d["version"] = rule.version
    return d


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.quantities.compute_quantities",
    bind=True,
    base=DeadLetterTask,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def compute_quantities(self, project_id: int, trace_id: str | None = None) -> dict:
    """Compute BOQ quantities for *project_id* via the dependency/rule engine.

    Pipeline
    --------
    1. Load project + analyzed drawings + detected objects + BOQ rules.
    2. Convert to plain dicts and expand via ``expand_with_dependencies()``.
    3. Write ``BOQItem`` rows (batched at 100).
    4. Create a ``CostVersion`` snapshot.
    5. Update project status to ``'estimating'``.
    6. Return a summary dict with counts and any errors/missing rules.
    """
    task_start = monotonic()
    task_id = self.request.id

    # Propagate trace_id into this task's context
    set_trace_id(trace_id)
    trace_id_val = get_trace_id()

    logger.info(
        "celery_task_start",
        task_name="app.tasks.quantities.compute_quantities",
        task_id=task_id,
        project_id=project_id,
        trace_id=trace_id_val,
    )

    async def _run() -> dict:
        # ------------------------------------------------------------------
        # Phase 1 — Load data from DB
        # ------------------------------------------------------------------
        async with async_session() as db:
            project = await db.get(Project, project_id)
            if project is None:
                msg = f"Project {project_id} not found"
                logger.error("project_not_found", project_id=project_id, task_id=task_id)
                return {"status": "error", "error": msg, "project_id": project_id, "task_id": task_id}

            # Fetch all analyzed (non-deleted) drawings
            stmt = select(Drawing).where(
                Drawing.project_id == project_id,
                Drawing.status == "analyzed",
                Drawing.is_deleted == False,
            )
            drawings = (await db.execute(stmt)).scalars().all()
            drawing_ids = [d.id for d in drawings]

            if not drawing_ids:
                logger.warning(
                    "no_analyzed_drawings",
                    project_id=project_id,
                    task_id=task_id,
                )
                return _empty_result(project_id, task_id, "No analyzed drawings found")

            # Fetch all detected objects across those drawings
            stmt = select(DetectedObject).where(
                DetectedObject.drawing_id.in_(drawing_ids),
                DetectedObject.is_deleted == False,
            )
            detected_objects = (await db.execute(stmt)).scalars().all()

            if not detected_objects:
                logger.warning(
                    "no_detected_objects",
                    project_id=project_id,
                    task_id=task_id,
                )
                return _empty_result(project_id, task_id, "No detected objects found")

            # Fetch all active BOQ rules
            stmt = select(BOQRule).where(BOQRule.is_active == True)
            rules = (await db.execute(stmt)).scalars().all()

            logger.info(
                "data_loaded",
                project_id=project_id,
                drawings=len(drawings),
                objects=len(detected_objects),
                rules=len(rules),
            )

            # Build quick-lookup: detected_object_id → drawing_id
            obj_id_to_drawing_id = {obj.id: obj.drawing_id for obj in detected_objects}

            # Remember values we'll need after the session closes
            project_currency = project.currency
            default_drawing_id = drawing_ids[0]

            # Convert to plain dicts for the (sync) rule engine
            detected_dicts = [_detected_to_dict(obj) for obj in detected_objects]
            rule_dicts = [_rule_to_dict(rule) for rule in rules]

        # ------------------------------------------------------------------
        # Phase 2 — Expand via dependency engine (no DB session needed)
        # ------------------------------------------------------------------
        logger.info(
            "expansion_start",
            object_count=len(detected_dicts),
            rule_count=len(rule_dicts),
        )

        items, report = expand_with_dependencies(
            detected_objects=detected_dicts,
            rules=rule_dicts,
        )

        logger.info(
            "expansion_complete",
            line_items=report.total_line_items,
            missing_rules=len(report.missing_rules),
            errors=len(report.errors),
        )

        for obj_type in report.missing_rules:
            logger.warning("missing_rule", object_type=obj_type)

        # Count detected objects by type for metrics
        obj_type_counts: dict[str, int] = {}
        for obj in detected_dicts:
            ot = obj.get("object_type", "unknown")
            obj_type_counts[ot] = obj_type_counts.get(ot, 0) + 1
        for ot, count in obj_type_counts.items():
            objects_detected.labels(object_type=ot).inc(count)

        boq_computed.inc()

        # ------------------------------------------------------------------
        # Phase 3 — Write BOQItem rows + CostVersion snapshot
        # ------------------------------------------------------------------
        async with async_session() as db:
            try:
                # --- 3a. Determine next version number ---
                version_result = await db.execute(
                    select(func.max(CostVersion.version_number)).where(
                        CostVersion.project_id == project_id,
                        CostVersion.is_deleted == False,
                    )
                )
                max_version = version_result.scalar() or 0
                next_version = max_version + 1

                # --- 3b. Write BOQItem rows ---
                written = 0
                for idx, item in enumerate(items):
                    # Resolve drawing_id from the source detected object.
                    # For synthetic (recursive) items the source_object_id
                    # chains back to the original detected object.
                    drawing_id = obj_id_to_drawing_id.get(item.source_object_id)
                    if drawing_id is None:
                        drawing_id = default_drawing_id  # safe fallback

                    boq_item = BOQItem(
                        project_id=project_id,
                        drawing_id=drawing_id,
                        object_id=item.source_object_id,
                        rule_id=item.rule_id,
                        description=item.description,
                        category=item.trade or _infer_category(
                            item.source_object_type,
                        ),
                        code=item.material_code,
                        material_name=item.material_name,
                        quantity=item.quantity,
                        unit=item.unit or "nos",
                        wastage_pct=item.wastage_pct,
                        total=item.total_qty,          # total quantity (incl. wastage)
                        hierarchy_level=item.hierarchy_level,
                        # Rates not yet loaded — set to 0, note "rates pending"
                        rate=0.0,
                        labour_rate=0.0,
                        transport_rate=0.0,
                        overhead_rate=0.0,
                        margin_rate=0.0,
                        base_cost=0.0,
                        total_cost=0.0,
                        revision=1,
                        sort_order=idx,
                    )
                    db.add(boq_item)
                    written += 1

                    if written % 100 == 0:
                        await db.commit()
                        logger.debug("boq_items_committed", count=written, project_id=project_id)

                if written % 100 != 0:
                    await db.commit()

                logger.info("boq_items_written", count=written, project_id=project_id)

                # --- 3c. Create CostVersion snapshot ---
                cost_version = CostVersion(
                    project_id=project_id,
                    version_number=next_version,
                    name="Auto-compute",
                    description="Auto-computed from BOQ rules. Rates pending.",
                    total_cost=0.0,
                    total_materials=0.0,
                    total_labour=0.0,
                    total_wastage=0.0,
                    total_transport=0.0,
                    total_overhead=0.0,
                    total_margin=0.0,
                    grand_total=0.0,
                    currency=project_currency,
                    status="draft",
                    created_by=0,  # system user until auth is wired
                )
                db.add(cost_version)
                await db.commit()
                await db.refresh(cost_version)

                logger.info(
                    "cost_version_created",
                    cost_version_id=cost_version.id,
                    version_number=cost_version.version_number,
                    project_id=project_id,
                )

                # --- 3d. Update project status → 'estimating' ---
                project = await db.get(Project, project_id)
                if project:
                    project.status = "estimating"
                    await db.commit()
                    logger.info("project_status_updated", project_id=project_id, status="estimating")

            except Exception as exc:
                await db.rollback()
                logger.error(
                    "boq_write_failed",
                    project_id=project_id,
                    error=str(exc),
                    exc_info=exc,
                )
                return {
                    "status": "error",
                    "error": str(exc),
                    "project_id": project_id,
                    "task_id": task_id,
                }

        # ------------------------------------------------------------------
        # Phase 4 — Return summary
        # ------------------------------------------------------------------
        duration_ms = (monotonic() - task_start) * 1000
        logger.info(
            "celery_task_finish",
            task_name="app.tasks.quantities.compute_quantities",
            task_id=task_id,
            project_id=project_id,
            duration_ms=round(duration_ms, 1),
            items_count=len(items),
            trace_id=trace_id_val,
        )
        return {
            "status": "completed",
            "project_id": project_id,
            "items_count": len(items),
            "cost_version_id": cost_version.id,
            "missing_rules": report.missing_rules,
            "errors": report.errors,
            "task_id": task_id,
        }

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_result(project_id: int, task_id: str, reason: str) -> dict:
    """Return a completed-but-empty result dict."""
    return {
        "status": "completed",
        "project_id": project_id,
        "items_count": 0,
        "cost_version_id": None,
        "missing_rules": [],
        "errors": [reason],
        "task_id": task_id,
    }


def _infer_category(object_type: str | None) -> str | None:
    """Derive a BOQ trade/category from a detected object type."""
    if not object_type:
        return None
    mapping = {
        "wall": "Civil",
        "floor": "Flooring",
        "ceiling": "Gypsum",
        "partition": "Gypsum",
        "door": "Carpentry",
        "window": "Glass",
        "column": "Structure",
        "beam": "Structure",
        "staircase": "Structure",
        "furniture": "Furniture",
        "duct": "HVAC",
        "pipe": "Plumbing",
        "cable_tray": "Electrical",
        "electrical_symbol": "Electrical",
        "hvac_symbol": "HVAC",
    }
    return mapping.get(object_type)
