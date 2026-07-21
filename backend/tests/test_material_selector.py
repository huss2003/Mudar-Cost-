"""Unit tests for app.services.material_selector.

Mocks the async DB session and patches SQLAlchemy ORM functions
at the module level to avoid a pre-existing mapper configuration
bug in the ``DetectedObject.parent/children`` relationship.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import _patch_sa


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_material(**kwargs) -> MagicMock:
    m = MagicMock()
    m.id = kwargs.get("id", 1)
    m.name = kwargs.get("name", "Vitrified Tile 600x600")
    m.brand = kwargs.get("brand", "Kajaria")
    m.sku = kwargs.get("sku", "VT-600")
    m.rate = kwargs.get("rate", 850.0)
    m.unit = kwargs.get("unit", "sqm")
    m.gst_rate = kwargs.get("gst_rate", 18.0)
    m.vendor_id = kwargs.get("vendor_id", 7)
    m.vendor = kwargs.get("vendor", None)
    if m.vendor is None:
        m.vendor = MagicMock()
        m.vendor.name = "Acme Supplies"
    m.lead_time_days = kwargs.get("lead_time_days", 7)
    m.warranty = kwargs.get("warranty", "2 years")
    m.fire_rating = kwargs.get("fire_rating", None)
    m.image_url = kwargs.get("image_url", None)
    m.min_order_qty = kwargs.get("min_order_qty", 10)
    m.category = kwargs.get("category", "Flooring")
    m.description = kwargs.get("description", "Premium vitrified tile")
    m.is_active = True
    return m


def _mock_boq_item(**kwargs) -> MagicMock:
    item = MagicMock()
    item.id = kwargs.get("id", 101)
    item.project_id = kwargs.get("project_id", 1)
    item.description = kwargs.get("description", "Tile flooring")
    item.quantity = kwargs.get("quantity", 100.0)
    item.rate = kwargs.get("rate", 850.0)
    item.total = kwargs.get("total", 85000.0)
    item.material_id = kwargs.get("material_id", None)
    item.material_name = kwargs.get("material_name", None)
    item.vendor_id = kwargs.get("vendor_id", None)
    item.category = kwargs.get("category", "Flooring")
    item.unit = kwargs.get("unit", "sqm")
    return item


def _mock_company_standard(value: str = "Kajaria") -> MagicMock:
    cs = MagicMock()
    cs.value = value
    return cs


# =========================================================================
# get_preferred_brands
# =========================================================================


class TestGetPreferredBrands:
    @pytest.mark.asyncio
    async def test_returns_brands(self):
        import app.services.material_selector as svc

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [
            _mock_company_standard("Kajaria"),
            _mock_company_standard("Somany"),
        ]
        db.execute.return_value = result_mock

        with _patch_sa(svc):
            brands = await svc.get_preferred_brands(db, "tiles")
        assert brands == ["Kajaria", "Somany"]

    @pytest.mark.asyncio
    async def test_empty(self):
        import app.services.material_selector as svc

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute.return_value = result_mock

        with _patch_sa(svc):
            brands = await svc.get_preferred_brands(db, "nonexistent")
        assert brands == []

    @pytest.mark.asyncio
    async def test_filters_none_values(self):
        import app.services.material_selector as svc

        cs_with_none = _mock_company_standard("")
        cs_with_none.value = None
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [
            _mock_company_standard("Kajaria"),
            cs_with_none,
        ]
        db.execute.return_value = result_mock

        with _patch_sa(svc):
            brands = await svc.get_preferred_brands(db, "tiles")
        assert brands == ["Kajaria"]


# =========================================================================
# get_material_options
# =========================================================================


class TestGetMaterialOptions:
    @pytest.mark.asyncio
    async def test_returns_options(self):
        import app.services.material_selector as svc

        db = AsyncMock()
        boq = _mock_boq_item(category="Flooring")
        boq_result = MagicMock()
        boq_result.scalar_one_or_none.return_value = boq
        mat_result = MagicMock()
        mat_result.unique.return_value.scalars.return_value.all.return_value = [
            _mock_material(id=1, name="Tile A"),
            _mock_material(id=2, name="Tile B"),
        ]
        db.execute.side_effect = [boq_result, mat_result]

        with _patch_sa(svc):
            options = await svc.get_material_options(db, 101)
        assert len(options) == 2
        assert options[0]["name"] in ("Tile A", "Tile B")
        assert "material_id" in options[0]
        assert "vendor_name" in options[0]

    @pytest.mark.asyncio
    async def test_boq_item_not_found(self):
        import app.services.material_selector as svc

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        with _patch_sa(svc):
            with pytest.raises(ValueError, match="BOQItem.*not found"):
                await svc.get_material_options(db, 999)

    @pytest.mark.asyncio
    async def test_fallback_keyword_search(self):
        import app.services.material_selector as svc

        db = AsyncMock()
        boq = _mock_boq_item(category="UnknownCat", description="porcelain tile floor")
        boq_result = MagicMock()
        boq_result.scalar_one_or_none.return_value = boq
        cat_result = MagicMock()
        cat_result.unique.return_value.scalars.return_value.all.return_value = []
        kw_result = MagicMock()
        kw_result.unique.return_value.scalars.return_value.all.return_value = [
            _mock_material(id=3, name="Porcelain Tile"),
        ]
        db.execute.side_effect = [boq_result, cat_result, kw_result]

        with _patch_sa(svc):
            options = await svc.get_material_options(db, 101)
        assert len(options) == 1
        assert options[0]["name"] == "Porcelain Tile"

    @pytest.mark.asyncio
    async def test_preferred_brands_sorted_first(self):
        import app.services.material_selector as svc

        db = AsyncMock()
        boq = _mock_boq_item(category="Flooring")
        boq_result = MagicMock()
        boq_result.scalar_one_or_none.return_value = boq
        mat_result = MagicMock()
        mat_result.unique.return_value.scalars.return_value.all.return_value = [
            _mock_material(id=1, name="Generic Tile", brand="NoName"),
            _mock_material(id=2, name="Kajaria Tile", brand="Kajaria"),
        ]
        db.execute.side_effect = [boq_result, mat_result]

        with _patch_sa(svc):
            options = await svc.get_material_options(db, 101, preferred_brands=["Kajaria"])
        assert options[0]["is_preferred"] is True
        assert options[0]["name"] == "Kajaria Tile"

    @pytest.mark.asyncio
    async def test_no_keywords_fallback(self):
        import app.services.material_selector as svc

        db = AsyncMock()
        boq = _mock_boq_item(category="UnknownCat", description="ab")
        boq_result = MagicMock()
        boq_result.scalar_one_or_none.return_value = boq
        cat_result = MagicMock()
        cat_result.unique.return_value.scalars.return_value.all.return_value = []
        db.execute.side_effect = [boq_result, cat_result]

        with _patch_sa(svc):
            options = await svc.get_material_options(db, 101)
        assert options == []


# =========================================================================
# select_material
# =========================================================================


class TestSelectMaterial:
    @pytest.mark.asyncio
    async def test_selects_material(self):
        import app.services.material_selector as svc

        db = AsyncMock()
        boq = _mock_boq_item(rate=500.0, quantity=100.0, project_id=1)
        material = _mock_material(rate=850.0, vendor_id=7)
        boq_result = MagicMock()
        boq_result.scalar_one_or_none.return_value = boq
        mat_result = MagicMock()
        mat_result.scalar_one_or_none.return_value = material
        cv_result = MagicMock()
        cv_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [boq_result, mat_result, cv_result]

        with _patch_sa(svc, extra={"RateHistory": MagicMock()}):
            result = await svc.select_material(db, 101, 1)
        assert result.material_id == 1
        assert result.material_name == "Vitrified Tile 600x600"
        assert result.rate == 850.0
        assert result.vendor_id == 7
        assert result.total == 85000.0
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_boq_item_not_found(self):
        import app.services.material_selector as svc

        db = AsyncMock()
        boq_result = MagicMock()
        boq_result.scalar_one_or_none.return_value = None
        db.execute.return_value = boq_result

        with _patch_sa(svc):
            with pytest.raises(ValueError, match="BOQItem.*not found"):
                await svc.select_material(db, 999, 1)

    @pytest.mark.asyncio
    async def test_material_not_found(self):
        import app.services.material_selector as svc

        db = AsyncMock()
        boq_result = MagicMock()
        boq_result.scalar_one_or_none.return_value = _mock_boq_item()
        mat_result = MagicMock()
        mat_result.scalar_one_or_none.return_value = None
        db.execute.side_effect = [boq_result, mat_result]

        with _patch_sa(svc):
            with pytest.raises(ValueError, match="Material.*not found"):
                await svc.select_material(db, 101, 999)

    @pytest.mark.asyncio
    async def test_downgrades_approved_versions(self):
        import app.services.material_selector as svc

        db = AsyncMock()
        boq = _mock_boq_item(rate=500.0, quantity=100.0, project_id=1)
        material = _mock_material(rate=850.0)
        boq_result = MagicMock()
        boq_result.scalar_one_or_none.return_value = boq
        mat_result = MagicMock()
        mat_result.scalar_one_or_none.return_value = material
        cv1 = MagicMock()
        cv1.status = "approved"
        cv_result = MagicMock()
        cv_result.scalars.return_value.all.return_value = [cv1]
        db.execute.side_effect = [boq_result, mat_result, cv_result]

        with _patch_sa(svc, extra={"RateHistory": MagicMock()}):
            await svc.select_material(db, 101, 1)
        assert cv1.status == "draft"


# =========================================================================
# find_alternatives
# =========================================================================


class TestFindAlternatives:
    @pytest.mark.asyncio
    async def test_returns_alternatives(self):
        import app.services.material_selector as svc

        db = AsyncMock()
        source = _mock_material(id=1, category="Flooring", rate=850.0)
        alt1 = _mock_material(id=2, name="Cheaper Tile", rate=700.0, category="Flooring")
        alt2 = _mock_material(id=3, name="Expensive Tile", rate=1000.0, category="Flooring")
        source_result = MagicMock()
        source_result.scalar_one_or_none.return_value = source
        alt_result = MagicMock()
        alt_result.unique.return_value.scalars.return_value.all.return_value = [alt1, alt2]
        db.execute.side_effect = [source_result, alt_result]

        with _patch_sa(svc):
            alternatives = await svc.find_alternatives(db, 1)
        assert len(alternatives) == 2
        assert alternatives[0]["rate"] == 700.0
        assert alternatives[1]["rate"] == 1000.0

    @pytest.mark.asyncio
    async def test_material_not_found(self):
        import app.services.material_selector as svc

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        with _patch_sa(svc):
            alternatives = await svc.find_alternatives(db, 999)
        assert alternatives == []

    @pytest.mark.asyncio
    async def test_no_alternatives(self):
        import app.services.material_selector as svc

        db = AsyncMock()
        source = _mock_material(id=1, category="UniqueCat", rate=850.0)
        source_result = MagicMock()
        source_result.scalar_one_or_none.return_value = source
        alt_result = MagicMock()
        alt_result.unique.return_value.scalars.return_value.all.return_value = []
        db.execute.side_effect = [source_result, alt_result]

        with _patch_sa(svc):
            alternatives = await svc.find_alternatives(db, 1)
        assert alternatives == []
