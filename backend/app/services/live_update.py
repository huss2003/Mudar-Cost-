"""In-process SSE event manager for live cost updates.

Maintains a per-project subscriber list using ``asyncio.Queue`` and provides
publish/subscribe primitives plus a specialised ``notify_material_change``
that recomputes a BOQ item's cost and pushes the update to all connected
clients.

Usage
-----
Subscribing (SSE endpoint)::

    queue = subscribe(project_id)
    # in an async generator:
    while True:
        msg = await queue.get()
        yield f"event: {msg['event']}\\ndata: {json.dumps(msg['data'])}\\n\\n"
    # on disconnect:
    unsubscribe(project_id, queue)

Publishing (after material selection)::

    asyncio.create_task(notify_material_change(project_id, boq_item_id))
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Subscriber registry: project_id -> list[asyncio.Queue]
# ---------------------------------------------------------------------------

_subscribers: dict[int, list[asyncio.Queue]] = defaultdict(list)


def subscribe(project_id: int) -> asyncio.Queue:
    """Register a new subscriber queue for *project_id*.

    Returns an :class:`asyncio.Queue` that the caller should consume in an
    infinite loop (typically from an SSE streaming response generator).
    """
    q: asyncio.Queue = asyncio.Queue()
    _subscribers[project_id].append(q)
    logger.debug(
        "SSE subscriber added for project %d (total=%d)",
        project_id,
        len(_subscribers[project_id]),
    )
    return q


def unsubscribe(project_id: int, queue: asyncio.Queue) -> None:
    """Remove *queue* from the subscriber list for *project_id*.

    Safe to call even if the project has no subscribers or the queue was
    already removed.
    """
    if project_id in _subscribers:
        before = len(_subscribers[project_id])
        _subscribers[project_id] = [
            q for q in _subscribers[project_id] if q is not queue
        ]
        after = len(_subscribers[project_id])
        if not _subscribers[project_id]:
            del _subscribers[project_id]
        logger.debug(
            "SSE subscriber removed for project %d (was %d, now %d)",
            project_id,
            before,
            after,
        )


async def publish(
    project_id: int,
    event: str,
    data: dict[str, Any],
) -> None:
    """Push an SSE message to every connected subscriber of *project_id*.

    Parameters
    ----------
    project_id:
        Target project identifier.
    event:
        SSE event type (e.g. ``\"material_changed\"``, ``\"cost_update\"``).
    data:
        JSON-serialisable payload.
    """
    message = {"event": event, "data": data}
    queues = _subscribers.get(project_id, [])
    if not queues:
        return
    logger.debug(
        "Publishing %s event to %d subscriber(s) for project %d",
        event,
        len(queues),
        project_id,
    )
    for q in queues:
        await q.put(message)


async def notify_material_change(project_id: int, boq_item_id: int) -> None:
    """Background task: recompute cost after a material selection and push SSE.

    Creates its own database session so it is safe to fire with
    ``asyncio.create_task()`` from inside a request handler without worrying
    about the request-level session being closed.

    Publishes two SSE events per call:

    - ``material_changed`` — lightweight update with the single line's new
      total and the new project-wide grand total.
    - ``cost_update`` — full trade-group aggregation + per-item cost
      breakdowns (compatible with ``compute_cost_version`` response shape).
    """
    from app.database import async_session
    from app.models.detection import BOQItem
    from app.models.reference import LabourRate
    from app.services.cost_engine import compute_line_item
    from sqlalchemy import select

    async with async_session() as db:
        try:
            # 1. Get the changed item
            item = await db.get(BOQItem, boq_item_id)
            if item is None or item.is_deleted:
                logger.warning(
                    "notify_material_change: BOQItem %d not found or deleted",
                    boq_item_id,
                )
                return

            # 2. Get all non-deleted items for the project
            stmt = (
                select(BOQItem)
                .where(
                    BOQItem.project_id == project_id,
                    BOQItem.is_deleted == False,
                )
            )
            result = await db.execute(stmt)
            all_items = result.scalars().all()

            # 3. Compute cost breakdowns for every line item
            breakdowns: list = []
            project_total = 0.0
            items_meta: list[dict[str, Any]] = []

            for bi in all_items:
                # Look up labour rate by trade (category)
                eff_labour: float | None = None
                if bi.category:
                    lr_stmt = (
                        select(LabourRate)
                        .where(
                            LabourRate.trade == bi.category,
                            LabourRate.is_deleted == False,
                        )
                        .limit(1)
                    )
                    lr_result = await db.execute(lr_stmt)
                    lr_obj = lr_result.scalar_one_or_none()
                    if lr_obj:
                        eff_labour = lr_obj.total_rate

                item_dict: dict[str, Any] = {
                    "id": bi.id,
                    "description": bi.description,
                    "quantity": bi.quantity,
                    "unit": bi.unit,
                    "rate": bi.rate or 0.0,
                    "wastage_pct": bi.wastage_pct or 0.0,
                    "trade": bi.category,
                    "total_qty": bi.quantity,
                    "material_id": bi.material_id,
                    "vendor_id": bi.vendor_id,
                    "discount_pct": bi.discount_pct or 0.0,
                    "gst_rate": bi.gst_rate or 18.0,
                    "labour_rate": bi.labour_rate or 0.0,
                    "transport_rate": bi.transport_rate or 0.0,
                    "transport_pct": bi.transport_pct or 5.0,
                    "overhead_pct": bi.overhead_pct or 10.0,
                    "margin_pct": bi.margin_pct or 15.0,
                }
                bd = compute_line_item(item_dict, eff_labour)
                breakdowns.append(bd)
                items_meta.append(item_dict)
                project_total += bd.grand_total

            # 4. Find the changed item's breakdown
            changed_breakdowns = [
                b for b in breakdowns if b.item_id == boq_item_id
            ]
            changed_bd = changed_breakdowns[0] if changed_breakdowns else None

            # 5. Build trade-group aggregations
            trade_groups: dict[str, dict[str, Any]] = {}
            for bd, meta in zip(breakdowns, items_meta):
                trade = str(meta.get("trade") or "other")
                if trade not in trade_groups:
                    trade_groups[trade] = {
                        "trade": trade,
                        "item_count": 0,
                        "subtotal": 0.0,
                    }
                trade_groups[trade]["item_count"] += 1
                trade_groups[trade]["subtotal"] += bd.grand_total

            for tg in trade_groups.values():
                tg["subtotal"] = round(tg["subtotal"], 2)

            # 6. Cost breakdowns in response-friendly format
            cost_breakdowns = [b.to_response() for b in breakdowns]

            # 7. Publish SSE events
            # 7a. Lightweight material-changed event
            await publish(
                project_id,
                "material_changed",
                {
                    "boq_item_id": boq_item_id,
                    "line_total": round(changed_bd.grand_total, 2) if changed_bd else 0.0,
                    "line_description": changed_bd.description if changed_bd else "",
                    "project_total": round(project_total, 2),
                    "total_items": len(breakdowns),
                },
            )

            # 7b. Full cost update (trade groups + breakdowns)
            await publish(
                project_id,
                "cost_update",
                {
                    "trade_groups": list(trade_groups.values()),
                    "cost_breakdowns": cost_breakdowns,
                    "project_total": round(project_total, 2),
                    "total_items": len(breakdowns),
                },
            )

            await db.commit()
            logger.info(
                "notify_material_change: published cost update for "
                "project %d, boq_item %d",
                project_id,
                boq_item_id,
            )

        except Exception:
            await db.rollback()
            logger.exception(
                "notify_material_change failed for project %d, boq_item %d",
                project_id,
                boq_item_id,
            )
