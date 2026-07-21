"""
Cost Engine — Pandas/NumPy cost calculator for BOQ line items.

Computes a full :class:`CostBreakdown` per line item using the shared cost
formula, aggregates line items into a cost version summary, and provides an
async function to recalculate a ``CostVersion`` row in the database.

Cost Formula
------------
For each ``BOQItem``::

    base_material_cost = rate * quantity
    wastage_cost = base_material_cost * (wastage_pct / 100)
    material_cost = base_material_cost + wastage_cost

    labour_cost = quantity * labour_rate_per_unit   (from LabourRate by trade)

    transport_cost = quantity * transport_rate_per_unit      # per-unit rate, OR
                   = material_cost * (transport_pct / 100)   # percentage fallback

    overhead_cost = material_cost * (overhead_pct / 100)

    subtotal = material_cost + labour_cost + transport_cost + overhead_cost
    margin_cost = subtotal * (margin_pct / 100)

    total_before_gst = subtotal + margin_cost
    discount_amount = total_before_gst * (discount_pct / 100)
    total_after_discount = total_before_gst - discount_amount

    gst_amount = total_after_discount * (gst_rate / 100)
    grand_total_line = total_after_discount + gst_amount
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import ROUND_HALF_UP, Decimal
from time import monotonic
from typing import Any

import structlog

from app.services.metrics import cost_engine_duration

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Cost Breakdown
# ---------------------------------------------------------------------------


@dataclass
class CostBreakdown:
    """Every computed cost field for a single BOQ line item."""

    item_id: int
    description: str
    quantity: float
    unit: str

    rate: float
    wastage_pct: float
    base_material_cost: float
    wastage_cost: float
    material_cost: float

    labour_rate: float
    labour_cost: float
    transport_cost: float
    overhead_pct: float
    overhead_cost: float

    subtotal: float
    margin_pct: float
    margin_cost: float

    total_before_gst: float
    discount_pct: float
    discount_amount: float
    total_after_discount: float

    gst_rate: float
    gst_amount: float
    grand_total: float

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary (useful for serialisation / DataFrame)."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def to_response(self) -> dict[str, Any]:
        """Return a shorter dict suitable for API responses."""
        return {
            "item_id": self.item_id,
            "description": self.description,
            "quantity": self.quantity,
            "unit": self.unit,
            "rate": self.rate,
            "material_cost": self.material_cost,
            "labour_cost": self.labour_cost,
            "transport_cost": self.transport_cost,
            "overhead_cost": self.overhead_cost,
            "margin_cost": self.margin_cost,
            "subtotal": self.subtotal,
            "discount_amount": self.discount_amount,
            "gst_amount": self.gst_amount,
            "grand_total": self.grand_total,
        }


# ---------------------------------------------------------------------------
# Rounding helper
# ---------------------------------------------------------------------------

_DECIMAL_PLACES = 2


def _r2(value: float) -> float:
    """Round to 2 decimal places using banker's rounding via Decimal."""
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(d)


# ---------------------------------------------------------------------------
# Single-line computation
# ---------------------------------------------------------------------------


def compute_line_item(
    item: dict,
    labour_rate: float | None = None,
) -> CostBreakdown:
    """Compute the full cost breakdown for a single BOQ line item.

    Parameters
    ----------
    item:
        A dictionary representation of a BOQ item.  Expected keys:

        - ``item_id`` or ``id``  (int) – item identifier
        - ``description``        (str)
        - ``quantity``           (float) – base quantity (before wastage)
        - ``unit``               (str)
        - ``rate``               (float) – material rate per unit
        - ``wastage_pct``        (float, optional) – default 0
        - ``labour_rate``        (float, optional) – per-unit labour rate
        - ``transport_rate``     (float, optional) – per-unit transport rate
        - ``transport_pct``      (float, optional) – transport % of material
        - ``overhead_pct``       (float, optional) – default 10
        - ``margin_pct``         (float, optional) – default 15
        - ``discount_pct``       (float, optional) – default 0
        - ``gst_rate``           (float, optional) – default 18

    labour_rate:
        Fallback labour rate per unit when the item does not carry one.
        Typically resolved from the ``LabourRate`` table by trade.

    Returns
    -------
    CostBreakdown
    """
    # ------------------------------------------------------------------
    # Extract & coerce fields with safe defaults
    # ------------------------------------------------------------------
    item_id: int = int(item.get("item_id") or item.get("id") or 0)
    description: str = str(item.get("description") or "")
    quantity: float = float(item.get("quantity") or 0.0)
    unit: str = str(item.get("unit") or "nos")

    rate: float = float(item.get("rate") or 0.0)
    wastage_pct: float = float(item.get("wastage_pct") or 0.0)

    # Labour rate: item-level takes precedence, then parameter, then 0
    item_labour_rate: float = float(item.get("labour_rate") or 0.0)
    eff_labour_rate: float = item_labour_rate or (labour_rate or 0.0)

    # Transport: per-unit rate OR percentage of material cost
    transport_rate: float = float(item.get("transport_rate") or 0.0)
    transport_pct: float = float(item.get("transport_pct") or 0.0)

    # Percentages with model-field defaults
    overhead_pct: float = float(item.get("overhead_pct") or item.get("overhead_rate") or 10.0)
    margin_pct: float = float(item.get("margin_pct") or item.get("margin_rate") or 15.0)
    discount_pct: float = float(item.get("discount_pct") or 0.0)
    gst_rate: float = float(item.get("gst_rate") or 18.0)

    # Guard against negative / zero quantity
    if quantity <= 0:
        quantity = 0.0

    # ------------------------------------------------------------------
    # Cost calculations (formula from shared contract)
    # ------------------------------------------------------------------
    base_material_cost = _r2(rate * quantity)
    wastage_cost = _r2(base_material_cost * (wastage_pct / 100.0))
    material_cost = _r2(base_material_cost + wastage_cost)

    labour_cost = _r2(quantity * eff_labour_rate)

    if transport_rate > 0:
        transport_cost = _r2(quantity * transport_rate)
    else:
        transport_cost = _r2(material_cost * (transport_pct / 100.0))

    overhead_cost = _r2(material_cost * (overhead_pct / 100.0))

    subtotal = _r2(material_cost + labour_cost + transport_cost + overhead_cost)
    margin_cost = _r2(subtotal * (margin_pct / 100.0))

    total_before_gst = _r2(subtotal + margin_cost)
    discount_amount = _r2(total_before_gst * (discount_pct / 100.0))
    total_after_discount = _r2(total_before_gst - discount_amount)

    gst_amount = _r2(total_after_discount * (gst_rate / 100.0))
    grand_total_line = _r2(total_after_discount + gst_amount)

    return CostBreakdown(
        item_id=item_id,
        description=description,
        quantity=quantity,
        unit=unit,
        rate=rate,
        wastage_pct=wastage_pct,
        base_material_cost=base_material_cost,
        wastage_cost=wastage_cost,
        material_cost=material_cost,
        labour_rate=eff_labour_rate,
        labour_cost=labour_cost,
        transport_cost=transport_cost,
        overhead_pct=overhead_pct,
        overhead_cost=overhead_cost,
        subtotal=subtotal,
        margin_pct=margin_pct,
        margin_cost=margin_cost,
        total_before_gst=total_before_gst,
        discount_pct=discount_pct,
        discount_amount=discount_amount,
        total_after_discount=total_after_discount,
        gst_rate=gst_rate,
        gst_amount=gst_amount,
        grand_total=grand_total_line,
    )


# ---------------------------------------------------------------------------
# Batch / version-level aggregation
# ---------------------------------------------------------------------------


def _aggregate_pandas(breakdowns: list[CostBreakdown]) -> dict[str, Any]:
    """Aggregate cost breakdowns using Pandas.

    Returns the same shape as :func:`_aggregate_python`.
    """
    try:
        import pandas as pd
    except ImportError:
        logger.warning("Pandas not available — falling back to pure-Python aggregation")
        return _aggregate_python(breakdowns)

    if not breakdowns:
        return _empty_aggregation()

    rows = [b.to_dict() for b in breakdowns]
    df = pd.DataFrame(rows)

    totals = {
        "total_materials": float(df["material_cost"].sum()),
        "total_labour": float(df["labour_cost"].sum()),
        "total_wastage": float(df["wastage_cost"].sum()),
        "total_transport": float(df["transport_cost"].sum()),
        "total_overhead": float(df["overhead_cost"].sum()),
        "total_margin": float(df["margin_cost"].sum()),
        "total_before_gst": float(
            (df["total_before_gst"]).sum()
        ),
        "total_discount": float(df["discount_amount"].sum()),
        "total_gst": float(df["gst_amount"].sum()),
        "grand_total": float(df["grand_total"].sum()),
        "item_count": len(df),
    }
    return {k: _r2(v) for k, v in totals.items()}


def _aggregate_python(breakdowns: list[CostBreakdown]) -> dict[str, Any]:
    """Pure-Python fallback aggregation (no Pandas dependency)."""
    if not breakdowns:
        return _empty_aggregation()

    totals = {
        "total_materials": 0.0,
        "total_labour": 0.0,
        "total_wastage": 0.0,
        "total_transport": 0.0,
        "total_overhead": 0.0,
        "total_margin": 0.0,
        "total_before_gst": 0.0,
        "total_discount": 0.0,
        "total_gst": 0.0,
        "grand_total": 0.0,
        "item_count": len(breakdowns),
    }
    for b in breakdowns:
        totals["total_materials"] += b.material_cost
        totals["total_labour"] += b.labour_cost
        totals["total_wastage"] += b.wastage_cost
        totals["total_transport"] += b.transport_cost
        totals["total_overhead"] += b.overhead_cost
        totals["total_margin"] += b.margin_cost
        totals["total_before_gst"] += b.total_before_gst
        totals["total_discount"] += b.discount_amount
        totals["total_gst"] += b.gst_amount
        totals["grand_total"] += b.grand_total

    return {k: _r2(v) if k != "item_count" else v for k, v in totals.items()}


def _empty_aggregation() -> dict[str, Any]:
    """Return a zero-filled aggregation dict."""
    return {
        "total_materials": 0.0,
        "total_labour": 0.0,
        "total_wastage": 0.0,
        "total_transport": 0.0,
        "total_overhead": 0.0,
        "total_margin": 0.0,
        "total_before_gst": 0.0,
        "total_discount": 0.0,
        "total_gst": 0.0,
        "grand_total": 0.0,
        "item_count": 0,
    }


def _group_trade_pandas(
    breakdowns: list[CostBreakdown],
    items_meta: list[dict],
) -> list[dict[str, Any]]:
    """Group cost breakdowns by trade using Pandas.

    Parameters
    ----------
    breakdowns:
        Cost breakdowns for each line item (same order as *items_meta*).
    items_meta:
        Item metadata dicts, each carrying at least a ``trade`` or ``category``
        key, plus ``item_id`` for alignment.

    Returns
    -------
    list[dict[str, Any]]
        One dict per trade group.
    """
    try:
        import pandas as pd
    except ImportError:
        return _group_trade_python(breakdowns, items_meta)

    if not breakdowns or not items_meta:
        return []

    # Build a DataFrame with breakdown fields + trade
    records = []
    for b, meta in zip(breakdowns, items_meta):
        trade = str(meta.get("trade") or meta.get("category") or "other")
        records.append(
            {
                "trade": trade,
                **b.to_dict(),
            }
        )

    df = pd.DataFrame(records)
    grouped = df.groupby("trade").agg(
        item_count=("item_id", "count"),
        total_materials=("material_cost", "sum"),
        total_labour=("labour_cost", "sum"),
        total_wastage=("wastage_cost", "sum"),
        total_transport=("transport_cost", "sum"),
        total_overhead=("overhead_cost", "sum"),
        total_margin=("margin_cost", "sum"),
        subtotal=("grand_total", "sum"),
    ).reset_index()

    groups = []
    for _, row in grouped.iterrows():
        groups.append(
            {
                "trade": row["trade"],
                "item_count": int(row["item_count"]),
                "total_materials": _r2(float(row["total_materials"])),
                "total_labour": _r2(float(row["total_labour"])),
                "total_wastage": _r2(float(row["total_wastage"])),
                "total_transport": _r2(float(row["total_transport"])),
                "total_overhead": _r2(float(row["total_overhead"])),
                "total_margin": _r2(float(row["total_margin"])),
                "subtotal": _r2(float(row["subtotal"])),
            }
        )

    return groups


def _group_trade_python(
    breakdowns: list[CostBreakdown],
    items_meta: list[dict],
) -> list[dict[str, Any]]:
    """Pure-Python trade grouping fallback."""
    trade_map: dict[str, dict] = {}
    for b, meta in zip(breakdowns, items_meta):
        trade = str(meta.get("trade") or meta.get("category") or "other")
        if trade not in trade_map:
            trade_map[trade] = {
                "trade": trade,
                "item_count": 0,
                "total_materials": 0.0,
                "total_labour": 0.0,
                "total_wastage": 0.0,
                "total_transport": 0.0,
                "total_overhead": 0.0,
                "total_margin": 0.0,
                "subtotal": 0.0,
            }
        g = trade_map[trade]
        g["item_count"] += 1
        g["total_materials"] += b.material_cost
        g["total_labour"] += b.labour_cost
        g["total_wastage"] += b.wastage_cost
        g["total_transport"] += b.transport_cost
        g["total_overhead"] += b.overhead_cost
        g["total_margin"] += b.margin_cost
        g["subtotal"] += b.grand_total

    for g in trade_map.values():
        for k in (
            "total_materials",
            "total_labour",
            "total_wastage",
            "total_transport",
            "total_overhead",
            "total_margin",
            "subtotal",
        ):
            g[k] = _r2(g[k])

    return list(trade_map.values())


def compute_cost_version(
    project_id: int,
    items: list[dict],
    *,
    use_pandas: bool = True,
    currency: str = "INR",
) -> dict[str, Any]:
    """Compute a full cost version summary from a list of BOQ item dicts.

    Parameters
    ----------
    project_id:
        Project identifier (carried through to the response).
    items:
        List of BOQ item dicts.  Each dict must contain the fields expected
        by :func:`compute_line_item`, plus optionally ``trade`` or
        ``category`` for grouping.
    use_pandas:
        If ``True`` (default), attempt Pandas aggregation; fall back to
        pure-Python if Pandas is not installed.
    currency:
        Currency code (default ``\"INR\"``).

    Returns
    -------
    dict
        ``{
            \"project_id\": int,
            \"trade_groups\": [...],
            \"cost_breakdowns\": [...],
            \"totals\": {...},
            \"grand_total\": float,
            \"currency\": str,
            \"item_count\": int,
        }``
    """
    if not items:
        return {
            "project_id": project_id,
            "trade_groups": [],
            "cost_breakdowns": [],
            "totals": _empty_aggregation(),
            "grand_total": 0.0,
            "currency": currency,
            "item_count": 0,
        }

    start = monotonic()

    # ------------------------------------------------------------------
    # 1. Compute every line item
    # ------------------------------------------------------------------
    breakdowns: list[CostBreakdown] = []
    items_meta: list[dict] = []
    for item in items:
        # Carry trade/category metadata for grouping
        items_meta.append(
            {
                "item_id": item.get("item_id") or item.get("id"),
                "trade": item.get("trade"),
                "category": item.get("category"),
            }
        )
        breakdowns.append(compute_line_item(item))

    logger.info(
        "cost_engine.line_items_computed",
        project_id=project_id,
        item_count=len(breakdowns),
    )

    # ------------------------------------------------------------------
    # 2. Aggregate totals
    # ------------------------------------------------------------------
    if use_pandas:
        totals = _aggregate_pandas(breakdowns)
    else:
        totals = _aggregate_python(breakdowns)

    # ------------------------------------------------------------------
    # 3. Group by trade
    # ------------------------------------------------------------------
    if use_pandas:
        trade_groups = _group_trade_pandas(breakdowns, items_meta)
    else:
        trade_groups = _group_trade_python(breakdowns, items_meta)

    duration_s = monotonic() - start
    cost_engine_duration.observe(duration_s)

    logger.info(
        "cost_engine.complete",
        project_id=project_id,
        item_count=totals["item_count"],
        grand_total=totals["grand_total"],
        duration_s=round(duration_s, 3),
    )

    return {
        "project_id": project_id,
        "trade_groups": trade_groups,
        "cost_breakdowns": [b.to_response() for b in breakdowns],
        "totals": totals,
        "grand_total": totals["grand_total"],
        "currency": currency,
        "item_count": totals["item_count"],
    }


# ---------------------------------------------------------------------------
# Database-level recalculate (async)
# ---------------------------------------------------------------------------


async def recalculate_cost_version(db: Any, cost_version_id: int) -> Any:
    """Reload all BOQItems for the version's project, recompute costs, and
    update the ``CostVersion`` row in the database.

    Parameters
    ----------
    db:
        An **async** SQLAlchemy session (``AsyncSession``).
    cost_version_id:
        Primary key of the ``CostVersion`` to recalculate.

    Returns
    -------
    CostVersion
        The updated ORM instance (already flushed to DB but not yet
        committed — the caller is responsible for ``db.commit()``).

    Raises
    ------
    ValueError
        If the ``CostVersion`` does not exist.
    """
    from sqlalchemy import select

    from app.models.detection import BOQItem, CostVersion
    from app.models.reference import LabourRate

    # 1. Load the cost version
    cost_version = await db.get(CostVersion, cost_version_id)
    if cost_version is None:
        raise ValueError(f"CostVersion {cost_version_id} not found")

    project_id = cost_version.project_id

    # 2. Load all BOQ items for this project
    stmt = (
        select(BOQItem)
        .where(
            BOQItem.project_id == project_id,
            BOQItem.is_deleted == False,  # noqa: E712
        )
        .order_by(BOQItem.id)
    )
    result = await db.execute(stmt)
    boq_items = list(result.scalars().all())

    if not boq_items:
        # No items — reset totals to zero
        cost_version.total_cost = 0.0
        cost_version.total_materials = 0.0
        cost_version.total_labour = 0.0
        cost_version.total_wastage = 0.0
        cost_version.total_transport = 0.0
        cost_version.total_overhead = 0.0
        cost_version.total_margin = 0.0
        cost_version.grand_total = 0.0
        await db.flush()
        return cost_version

    # 3. Build a trade → labour_rate lookup
    #    (load all active labour rates and index by trade)
    labour_stmt = select(LabourRate).where(LabourRate.is_deleted == False)  # noqa: E712
    labour_result = await db.execute(labour_stmt)
    all_labour_rates = list(labour_result.scalars().all())

    labour_rate_by_trade: dict[str, float] = {}
    for lr in all_labour_rates:
        trade = (lr.trade or "").lower()
        # Keep the first entry per trade (or the one with highest total_rate)
        if trade not in labour_rate_by_trade or lr.total_rate > labour_rate_by_trade[trade]:
            labour_rate_by_trade[trade] = lr.total_rate

    # 4. Build item dicts and compute breakdowns
    item_dicts: list[dict] = []
    for boq in boq_items:
        trade = (boq.category or "other").lower()
        effective_labour_rate = labour_rate_by_trade.get(trade) or boq.labour_rate or 0.0

        item_dicts.append(
            {
                "id": boq.id,
                "item_id": boq.id,
                "description": boq.description,
                "quantity": boq.quantity,
                "unit": boq.unit,
                "rate": boq.rate,
                "wastage_pct": boq.wastage_pct,
                "labour_rate": effective_labour_rate,
                "transport_rate": boq.transport_rate,
                "transport_pct": boq.transport_pct,
                "overhead_pct": boq.overhead_pct,
                "margin_pct": boq.margin_pct,
                "discount_pct": boq.discount_pct,
                "gst_rate": boq.gst_rate,
                "trade": trade,
                "category": boq.category,
            }
        )

    breakdowns = [compute_line_item(it) for it in item_dicts]
    totals = _aggregate_python(breakdowns)  # always use pure-Python inside DB ops

    # 5. Update CostVersion fields
    cost_version.total_cost = totals["total_materials"]
    cost_version.total_materials = totals["total_materials"]
    cost_version.total_labour = totals["total_labour"]
    cost_version.total_wastage = totals["total_wastage"]
    cost_version.total_transport = totals["total_transport"]
    cost_version.total_overhead = totals["total_overhead"]
    cost_version.total_margin = totals["total_margin"]
    cost_version.grand_total = totals["grand_total"]

    await db.flush()
    return cost_version
