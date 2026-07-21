"""Comprehensive unit tests for app.services.cost_engine.

Covers:
- compute_line_item with known inputs and edge cases
- CostBreakdown serialisation methods
- _aggregate_python / _aggregate_pandas / _empty_aggregation
- _group_trade_python / _group_trade_pandas
- compute_cost_version (empty, single item, multiple items)
- recalculate_cost_version (async, mock DB)
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.cost_engine import (
    CostBreakdown,
    _aggregate_pandas,
    _aggregate_python,
    _empty_aggregation,
    _group_trade_pandas,
    _group_trade_python,
    _r2,
    compute_cost_version,
    compute_line_item,
    recalculate_cost_version,
)


# =========================================================================
# Helper: known-input item dicts
# =========================================================================


def _tile_item(**overrides) -> dict:
    """Standard vitrified tile line item (850/sq.m, qty 10, 10% wastage,
    labour 800/unit, 10% discount, 18% GST)."""
    base = {
        "item_id": 1,
        "description": "Vitrified tile flooring",
        "quantity": 10.0,
        "unit": "sqm",
        "rate": 850.0,
        "wastage_pct": 10.0,
        "labour_rate": 800.0,
        "transport_rate": 0.0,
        "transport_pct": 0.0,
        "overhead_pct": 10.0,
        "margin_pct": 15.0,
        "discount_pct": 10.0,
        "gst_rate": 18.0,
        "trade": "Flooring",
        "category": "Flooring",
    }
    base.update(overrides)
    return base


# =========================================================================
# _r2
# =========================================================================


class TestRound2:
    def test_basic_rounding(self):
        assert _r2(123.456) == 123.46
        assert _r2(123.454) == 123.45

    def test_bankers_rounding(self):
        # ROUND_HALF_UP: 2.5 rounded to 2 decimal places is 2.50 → 2.5
        assert _r2(2.5) == 2.5

    def test_integer(self):
        assert _r2(100) == 100.0

    def test_zero(self):
        assert _r2(0.0) == 0.0


# =========================================================================
# compute_line_item
# =========================================================================


class TestComputeLineItem:
    """Verify every field of the CostBreakdown dataclass."""

    def test_full_computation(self):
        """Known input → known output.
        material=850, qty=10, wastage=10% → base=8500, wastage=850, material=9350
        labour_rate=800 → labour_cost=8000
        overhead=10% → overhead=935
        margin=15% → margin=(9350+8000+0+935)*0.15 = 2742.75
        discount=10%, gst=18%
        """
        bd = compute_line_item(_tile_item())
        assert isinstance(bd, CostBreakdown)

        # --- Material chain ---
        assert bd.rate == 850.0
        assert bd.quantity == 10.0
        assert bd.base_material_cost == 8500.0  # 850 * 10
        assert bd.wastage_pct == 10.0
        assert bd.wastage_cost == 850.0  # 8500 * 10%
        assert bd.material_cost == 9350.0  # 8500 + 850

        # --- Labour ---
        assert bd.labour_rate == 800.0
        assert bd.labour_cost == 8000.0  # 10 * 800

        # --- Transport ---
        assert bd.transport_cost == 0.0

        # --- Overhead ---
        assert bd.overhead_pct == 10.0
        assert bd.overhead_cost == 935.0  # 9350 * 10%

        # --- Subtotal & Margin ---
        # subtotal = 9350 + 8000 + 0 + 935 = 18285
        assert bd.subtotal == 18285.0
        assert bd.margin_pct == 15.0
        assert bd.margin_cost == 2742.75  # 18285 * 15%

        # --- GST chain ---
        # total_before_gst = 18285 + 2742.75 = 21027.75
        assert bd.total_before_gst == 21027.75
        assert bd.discount_pct == 10.0
        # discount = 21027.75 * 10% = 2102.78 (round to 2)
        assert bd.discount_amount == 2102.78
        # total_after_discount = 21027.75 - 2102.78 = 18924.97
        assert bd.total_after_discount == 18924.97
        # gst = 18924.97 * 18% = 3406.49 (round)
        assert bd.gst_amount == 3406.49
        # grand_total = 18924.97 + 3406.49 = 22331.46
        assert bd.grand_total == 22331.46

    def test_zero_rate(self):
        """With rate=0 the material chain is 0, but labour/overhead/margin
        still apply based on quantity."""
        bd = compute_line_item(_tile_item(rate=0.0))
        assert bd.rate == 0.0
        assert bd.base_material_cost == 0.0
        assert bd.material_cost == 0.0
        # Labour, overhead, margin still computed on quantity
        assert bd.labour_cost > 0  # qty=10 * 800 = 8000
        assert bd.grand_total > 0

    def test_missing_labour_rate(self):
        """When neither the item nor the parameter provides a labour rate,
        labour_rate defaults to 0."""
        item = _tile_item(labour_rate=None)
        del item["labour_rate"]
        bd = compute_line_item(item, labour_rate=None)
        assert bd.labour_rate == 0.0
        assert bd.labour_cost == 0.0

    def test_labour_rate_from_parameter(self):
        """When the item has no labour_rate but a fallback is provided."""
        item = _tile_item(labour_rate=None)
        del item["labour_rate"]
        bd = compute_line_item(item, labour_rate=500.0)
        assert bd.labour_rate == 500.0
        assert bd.labour_cost == 5000.0

    def test_item_labour_rate_overrides_parameter(self):
        """Item-level labour_rate takes precedence over the parameter."""
        bd = compute_line_item(_tile_item(labour_rate=1000.0), labour_rate=500.0)
        assert bd.labour_rate == 1000.0
        assert bd.labour_cost == 10000.0

    def test_transport_rate_per_unit(self):
        """transport_rate > 0 uses per-unit calculation."""
        bd = compute_line_item(_tile_item(transport_rate=50.0))
        assert bd.transport_cost == 500.0  # 10 * 50

    def test_transport_pct_fallback(self):
        """transport_rate = 0 falls back to percentage of material cost."""
        bd = compute_line_item(_tile_item(transport_rate=0.0, transport_pct=5.0))
        # material_cost=9350, transport=9350*5%=467.5
        assert bd.transport_cost == 467.5

    def test_negative_quantity_guarded(self):
        """Negative quantity is clamped to 0."""
        bd = compute_line_item(_tile_item(quantity=-5.0))
        assert bd.quantity == 0.0
        assert bd.base_material_cost == 0.0
        assert bd.grand_total == 0.0

    def test_item_id_fallback_to_id(self):
        """Uses 'id' key when 'item_id' is absent."""
        item = _tile_item()
        del item["item_id"]
        item["id"] = 99
        bd = compute_line_item(item)
        assert bd.item_id == 99

    def test_default_unit(self):
        """Defaults to 'nos' when unit is missing."""
        bd = compute_line_item(_tile_item(unit=None))
        assert bd.unit == "nos"

    def test_default_overhead_pct(self):
        """Defaults to 10% when overhead_pct is omitted."""
        bd = compute_line_item(_tile_item(overhead_pct=None))
        assert bd.overhead_pct == 10.0

    def test_default_margin_pct(self):
        """Defaults to 15% when margin_pct is omitted."""
        bd = compute_line_item(_tile_item(margin_pct=None))
        assert bd.margin_pct == 15.0

    def test_default_gst_rate(self):
        """Defaults to 18% when gst_rate is omitted."""
        bd = compute_line_item(_tile_item(gst_rate=None))
        assert bd.gst_rate == 18.0

    def test_empty_description(self):
        """Empty description doesn't crash."""
        bd = compute_line_item(_tile_item(description=None))
        assert bd.description == ""

    def test_overhead_rate_alias(self):
        """overhead_rate works as an alias for overhead_pct."""
        bd = compute_line_item(_tile_item(overhead_pct=None, overhead_rate=12.0))
        assert bd.overhead_pct == 12.0

    def test_margin_rate_alias(self):
        """margin_rate works as an alias for margin_pct."""
        bd = compute_line_item(_tile_item(margin_pct=None, margin_rate=20.0))
        assert bd.margin_pct == 20.0


# =========================================================================
# CostBreakdown serialisation
# =========================================================================


class TestCostBreakdown:
    def test_to_dict_contains_all_fields(self):
        bd = compute_line_item(_tile_item())
        d = bd.to_dict()
        assert isinstance(d, dict)
        assert d["item_id"] == 1
        assert d["grand_total"] == bd.grand_total
        assert d["description"] == "Vitrified tile flooring"
        # All dataclass fields
        assert len(d) == len([f.name for f in CostBreakdown.__dataclass_fields__.values()])

    def test_to_response_contains_expected_keys(self):
        bd = compute_line_item(_tile_item())
        r = bd.to_response()
        expected_keys = {
            "item_id", "description", "quantity", "unit", "rate",
            "material_cost", "labour_cost", "transport_cost",
            "overhead_cost", "margin_cost", "subtotal",
            "discount_amount", "gst_amount", "grand_total",
        }
        assert set(r.keys()) == expected_keys
        assert r["grand_total"] == bd.grand_total


# =========================================================================
# Aggregation
# =========================================================================


class TestAggregateEmpty:
    def test_empty_aggregation(self):
        agg = _empty_aggregation()
        assert agg["grand_total"] == 0.0
        assert agg["item_count"] == 0
        assert agg["total_materials"] == 0.0
        assert all(v == 0.0 for k, v in agg.items() if k != "item_count")

    def test_aggregate_python_empty(self):
        assert _aggregate_python([]) == _empty_aggregation()

    def test_aggregate_pandas_empty(self):
        assert _aggregate_pandas([]) == _empty_aggregation()


class TestAggregatePython:
    def test_single_item(self):
        bd = compute_line_item(_tile_item())
        agg = _aggregate_python([bd])
        assert agg["item_count"] == 1
        assert agg["total_materials"] == bd.material_cost
        assert agg["grand_total"] == bd.grand_total

    def test_two_items(self):
        bd1 = compute_line_item(_tile_item(item_id=1, quantity=10.0))
        bd2 = compute_line_item(_tile_item(item_id=2, quantity=20.0))
        agg = _aggregate_python([bd1, bd2])
        assert agg["item_count"] == 2
        assert agg["total_materials"] == _r2(bd1.material_cost + bd2.material_cost)
        assert agg["grand_total"] == _r2(bd1.grand_total + bd2.grand_total)

    def test_many_items_sums_match(self):
        bds = [
            compute_line_item(_tile_item(item_id=i, quantity=float(i * 10)))
            for i in range(1, 6)
        ]
        agg = _aggregate_python(bds)
        assert agg["item_count"] == 5
        expected_grand = _r2(sum(b.grand_total for b in bds))
        assert agg["grand_total"] == expected_grand


class TestAggregatePandas:
    def test_with_pandas_available(self):
        """When pandas is available, _aggregate_pandas returns the same
        shape as _aggregate_python."""
        pandas = pytest.importorskip("pandas")
        bd = compute_line_item(_tile_item())
        agg = _aggregate_pandas([bd])
        assert agg["item_count"] == 1
        assert agg["grand_total"] == bd.grand_total

    def test_pandas_fallback(self):
        """When pandas is not available, _aggregate_pandas falls back
        to pure-Python."""
        with patch.dict("sys.modules", {"pandas": None}):
            # Force reimport by calling the function — the try/except will fire
            bd = compute_line_item(_tile_item())
            agg = _aggregate_pandas([bd])
            assert agg["item_count"] == 1
            assert agg["grand_total"] == bd.grand_total


# =========================================================================
# Trade grouping
# =========================================================================


class TestGroupTradePython:
    def test_single_trade(self):
        bd = compute_line_item(_tile_item())
        meta = [{"item_id": 1, "trade": "Flooring", "category": "Flooring"}]
        groups = _group_trade_python([bd], meta)
        assert len(groups) == 1
        assert groups[0]["trade"] == "Flooring"
        assert groups[0]["item_count"] == 1
        assert groups[0]["total_materials"] == bd.material_cost

    def test_two_trades(self):
        bd1 = compute_line_item(_tile_item(item_id=1, trade="Flooring", category="Flooring"))
        bd2 = compute_line_item(
            _tile_item(item_id=2, trade="Painting", category="Painting", rate=200.0)
        )
        meta = [
            {"item_id": 1, "trade": "Flooring", "category": "Flooring"},
            {"item_id": 2, "trade": "Painting", "category": "Painting"},
        ]
        groups = _group_trade_python([bd1, bd2], meta)
        assert len(groups) == 2
        trade_names = {g["trade"] for g in groups}
        assert trade_names == {"Flooring", "Painting"}

    def test_empty(self):
        assert _group_trade_python([], []) == []

    def test_fallback_to_category(self):
        """Uses 'category' when 'trade' is missing."""
        bd = compute_line_item(_tile_item())
        meta = [{"item_id": 1, "category": "Flooring"}]
        groups = _group_trade_python([bd], meta)
        assert len(groups) == 1
        assert groups[0]["trade"] == "Flooring"

    def test_fallback_to_other(self):
        """Defaults to 'other' when both trade and category are missing."""
        bd = compute_line_item(_tile_item())
        meta = [{"item_id": 1}]
        groups = _group_trade_python([bd], meta)
        assert len(groups) == 1
        assert groups[0]["trade"] == "other"


class TestGroupTradePandas:
    def test_with_pandas(self):
        pandas = pytest.importorskip("pandas")
        bd = compute_line_item(_tile_item())
        meta = [{"item_id": 1, "trade": "Flooring", "category": "Flooring"}]
        groups = _group_trade_pandas([bd], meta)
        assert len(groups) == 1
        assert groups[0]["trade"] == "Flooring"

    def test_empty(self):
        assert _group_trade_pandas([], []) == []


# =========================================================================
# compute_cost_version
# =========================================================================


class TestComputeCostVersion:
    def test_empty_items(self):
        result = compute_cost_version(project_id=1, items=[], use_pandas=False)
        assert result["project_id"] == 1
        assert result["trade_groups"] == []
        assert result["cost_breakdowns"] == []
        assert result["totals"]["item_count"] == 0
        assert result["grand_total"] == 0.0
        assert result["currency"] == "INR"

    def test_single_item(self):
        item = _tile_item()
        result = compute_cost_version(project_id=1, items=[item], use_pandas=False)
        assert result["project_id"] == 1
        assert len(result["cost_breakdowns"]) == 1
        assert result["cost_breakdowns"][0]["grand_total"] > 0
        assert len(result["trade_groups"]) == 1
        assert result["totals"]["item_count"] == 1
        assert result["grand_total"] > 0

    def test_multiple_items(self):
        items = [
            _tile_item(item_id=1, quantity=10.0, trade="Flooring"),
            _tile_item(item_id=2, quantity=20.0, trade="Flooring"),
            _tile_item(item_id=3, quantity=5.0, trade="Painting", rate=200.0),
        ]
        result = compute_cost_version(project_id=1, items=items, use_pandas=False)
        assert result["totals"]["item_count"] == 3
        assert len(result["trade_groups"]) == 2
        assert result["grand_total"] > 0

    def test_currency_param(self):
        item = _tile_item()
        result = compute_cost_version(project_id=1, items=[item], currency="USD")
        assert result["currency"] == "USD"

    def test_use_pandas_true(self):
        item = _tile_item()
        result = compute_cost_version(project_id=1, items=[item], use_pandas=True)
        assert result["totals"]["item_count"] == 1
        assert result["grand_total"] > 0


# =========================================================================
# recalculate_cost_version (async, mock DB)
# =========================================================================


class TestRecalculateCostVersion:
    @pytest.mark.asyncio
    async def test_cost_version_not_found(self):
        """Raises ValueError when CostVersion does not exist."""
        db = AsyncMock()
        db.get.return_value = None

        with pytest.raises(ValueError, match="CostVersion.*not found"):
            await recalculate_cost_version(db, cost_version_id=999)

    @pytest.mark.asyncio
    async def test_empty_boq_resets_totals(self):
        """When no BOQ items exist, totals reset to zero."""
        cv = MagicMock()
        cv.id = 1
        cv.project_id = 1
        cv.total_cost = 999.0
        cv.total_materials = 999.0
        cv.total_labour = 999.0
        cv.total_wastage = 999.0
        cv.total_transport = 999.0
        cv.total_overhead = 999.0
        cv.total_margin = 999.0
        cv.grand_total = 999.0

        db = AsyncMock()
        db.get.return_value = cv

        # No BOQ items — return empty list from execute
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute.return_value = result_mock

        result = await recalculate_cost_version(db, cost_version_id=1)
        assert result.total_cost == 0.0
        assert result.grand_total == 0.0
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_boq_items(self):
        """Recalculates totals from BOQ items."""
        cv = MagicMock()
        cv.id = 1
        cv.project_id = 1
        cv.total_cost = 0.0
        cv.total_materials = 0.0
        cv.total_labour = 0.0
        cv.total_wastage = 0.0
        cv.total_transport = 0.0
        cv.total_overhead = 0.0
        cv.total_margin = 0.0
        cv.grand_total = 0.0

        # Mock a BOQItem
        boq = MagicMock()
        boq.id = 101
        boq.description = "Test item"
        boq.quantity = 10.0
        boq.unit = "sqm"
        boq.rate = 500.0
        boq.wastage_pct = 5.0
        boq.labour_rate = None
        boq.transport_rate = 0.0
        boq.transport_pct = 0.0
        boq.overhead_pct = 10.0
        boq.margin_pct = 15.0
        boq.discount_pct = 0.0
        boq.gst_rate = 18.0
        boq.category = "Flooring"
        boq.is_deleted = False

        db = AsyncMock()
        db.get.return_value = cv

        # First execute call returns BOQ items; second returns LabourRate list
        boq_result = MagicMock()
        boq_result.scalars.return_value.all.return_value = [boq]

        labour_result = MagicMock()
        labour_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [boq_result, labour_result]

        result = await recalculate_cost_version(db, cost_version_id=1)
        assert result.total_materials > 0
        assert result.grand_total > 0
        db.flush.assert_awaited_once()
