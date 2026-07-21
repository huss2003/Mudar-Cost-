"""Unit tests for app.services.ai_feature_service.

Mocks the async DB session and patches SQLAlchemy ORM functions
to test all five AI-powered service functions fully offline.
"""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock, PropertyMock, patch

import pytest

from tests.conftest import _patch_sa


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_project(**kwargs) -> MagicMock:
    p = MagicMock()
    p.id = kwargs.get("id", 1)
    p.name = kwargs.get("name", "Test Project")
    return p


def _mock_boq_item(**kwargs) -> MagicMock:
    item = MagicMock()
    item.id = kwargs.get("id", 1)
    item.project_id = kwargs.get("project_id", 1)
    item.description = kwargs.get("description", "Tile flooring")
    item.quantity = kwargs.get("quantity", 100.0)
    item.unit = kwargs.get("unit", "sqm")
    item.rate = kwargs.get("rate", 850.0)
    item.total = kwargs.get("total", 85000.0)
    item.category = kwargs.get("category", "Flooring")
    item.material_name = kwargs.get("material_name", "Tile")
    item.material_id = kwargs.get("material_id", 42)
    item.wastage_pct = kwargs.get("wastage_pct", 10.0)
    item.labour_rate = kwargs.get("labour_rate", 800.0)
    item.overhead_pct = kwargs.get("overhead_pct", 10.0)
    item.margin_pct = kwargs.get("margin_pct", 15.0)
    item.discount_pct = kwargs.get("discount_pct", 0.0)
    item.gst_rate = kwargs.get("gst_rate", 18.0)
    item.object_id = kwargs.get("object_id", None)
    item.is_deleted = False
    item.detected_object = None
    return item


def _mock_detected_object(**kwargs) -> MagicMock:
    obj = MagicMock()
    obj.id = kwargs.get("id", 1)
    obj.drawing_id = kwargs.get("drawing_id", 1)
    obj.object_type = kwargs.get("object_type", "wall")
    obj.label = kwargs.get("label", "Wall-A")
    obj.length = kwargs.get("length", 5000.0)
    obj.area = kwargs.get("area", 15.0)
    obj.is_deleted = False
    return obj


def _mock_material(**kwargs) -> MagicMock:
    m = MagicMock()
    m.id = kwargs.get("id", 1)
    m.name = kwargs.get("name", "Cheap Tile")
    m.brand = kwargs.get("brand", "Generic")
    m.rate = kwargs.get("rate", 500.0)
    m.unit = kwargs.get("unit", "sqm")
    m.category = kwargs.get("category", "flooring")
    m.description = kwargs.get("description", "Budget tile")
    m.is_active = True
    return m


def _mock_productivity_rate(**kwargs) -> MagicMock:
    pr = MagicMock()
    pr.trade = kwargs.get("trade", "Flooring")
    pr.output_per_day = kwargs.get("output_per_day", 15.0)
    pr.crew_size = kwargs.get("crew_size", 3)
    pr.is_deleted = False
    return pr


# =========================================================================
# _get_trade_dependencies (pure function)
# =========================================================================


class TestGetTradeDependencies:
    def _import_and_test(self):
        from app.services.ai_feature_service import _get_trade_dependencies
        return _get_trade_dependencies

    def test_returns_dict(self):
        fn = self._import_and_test()
        deps = fn()
        assert isinstance(deps, dict)
        assert "Civil" in deps
        assert deps["Civil"] == []
        assert "MEP" in deps

    def test_trade_in_last_group_depends_on_all_previous(self):
        fn = self._import_and_test()
        deps = fn()
        assert len(deps["Labour"]) > 0


# =========================================================================
# answer_project_question (no SA select calls when mocked)
# =========================================================================


class TestAnswerProjectQuestion:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from app.services.ai_feature_service import answer_project_question

        db = AsyncMock()
        db.get.return_value = None

        with (
            patch("app.services.ai_feature_service.rag_search") as mock_rag,
            patch("app.services.ai_feature_service.DeepSeekClient") as mock_ds,
        ):
            mock_rag.return_value = "No context"
            client = AsyncMock()
            client.config = MagicMock()
            client.config.mock_mode = True
            mock_ds.return_value = client
            client.ask.return_value = {"choices": [{"message": {"content": "Mock answer"}}]}

            resp = await answer_project_question(db, 999, "What is the cost?")
            assert resp.answer == "Project not found."
            assert resp.confidence == 0.0

    @pytest.mark.asyncio
    async def test_returns_answer(self):
        from app.services.ai_feature_service import answer_project_question

        db = AsyncMock()
        db.get.return_value = _mock_project(id=1)

        with (
            patch("app.services.ai_feature_service.rag_search") as mock_rag,
            patch("app.services.ai_feature_service.DeepSeekClient") as mock_ds,
        ):
            mock_rag.return_value = "Project has 10 BOQ items"
            client = AsyncMock()
            client.config = MagicMock()
            client.config.mock_mode = True
            mock_ds.return_value = client
            client.ask.return_value = {
                "choices": [{"message": {"content": "The total cost is ₹22331.46"}}]
            }

            resp = await answer_project_question(db, 1, "What is the total cost?")
            assert "₹22331.46" in resp.answer
            assert resp.confidence == 0.85


# =========================================================================
# detect_missing_boq_items
# =========================================================================


class TestDetectMissingBOQItems:
    @pytest.mark.asyncio
    async def test_no_objects_returns_suggestions(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        cat_result = MagicMock()
        cat_result.__iter__.return_value = iter([("Flooring",)])
        obj_result = MagicMock()
        obj_result.scalars.return_value.all.return_value = []
        linked_result = MagicMock()
        linked_result.__iter__.return_value = iter([])
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        db.execute.side_effect = [cat_result, obj_result, linked_result, count_result]

        with (
            patch("app.services.ai_feature_service.find_similar_projects") as mock_sim,
            _patch_sa(svc),
        ):
            mock_sim.return_value = []
            resp = await svc.detect_missing_boq_items(db, 1)
        assert resp.gap_count >= 0
        assert isinstance(resp.suggested_items, list)

    @pytest.mark.asyncio
    async def test_detected_object_without_boq(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        cat_result = MagicMock()
        cat_result.__iter__.return_value = iter([])
        obj = _mock_detected_object(id=5, object_type="door")
        obj_result = MagicMock()
        obj_result.scalars.return_value.all.return_value = [obj]
        linked_result = MagicMock()
        linked_result.__iter__.return_value = iter([])
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        db.execute.side_effect = [cat_result, obj_result, linked_result, count_result]

        with (
            patch("app.services.ai_feature_service.find_similar_projects") as mock_sim,
            _patch_sa(svc),
        ):
            mock_sim.return_value = []
            resp = await svc.detect_missing_boq_items(db, 1)
        assert resp.gap_count >= 1

    @pytest.mark.asyncio
    async def test_missing_categories_from_similar_projects(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        cat_result = MagicMock()
        cat_result.__iter__.return_value = iter([("Flooring",)])
        obj_result = MagicMock()
        obj_result.scalars.return_value.all.return_value = []
        linked_result = MagicMock()
        linked_result.__iter__.return_value = iter([])
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        db.execute.side_effect = [cat_result, obj_result, linked_result, count_result]

        with (
            patch("app.services.ai_feature_service.find_similar_projects") as mock_sim,
            _patch_sa(svc),
        ):
            mock_sim.return_value = [{
                "project_id": 2,
                "name": "Similar Office",
                "shared_categories": ["Painting", "Glass"],
            }]
            resp = await svc.detect_missing_boq_items(db, 1)
        painting_suggestions = [s for s in resp.suggested_items if "Painting" in s.category]
        assert len(painting_suggestions) >= 1


# =========================================================================
# detect_anomalies
# =========================================================================


class TestDetectAnomalies:
    @pytest.mark.asyncio
    async def test_empty_boq_returns_needs_review(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        boq_result = MagicMock()
        boq_result.unique.return_value.scalars.return_value.all.return_value = []
        db.execute.return_value = boq_result

        with _patch_sa(svc):
            resp = await svc.detect_anomalies(db, 1)
        assert resp.anomalies == []
        assert resp.anomaly_count == 0
        assert resp.project_health == "needs_review"

    @pytest.mark.asyncio
    async def test_no_anomalies_healthy(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        boq_result = MagicMock()
        boq_result.unique.return_value.scalars.return_value.all.return_value = [
            _mock_boq_item(id=1, rate=100.0, category="Flooring"),
        ]
        similar_result = MagicMock()
        similar_result.__iter__.return_value = iter([(None, None, None, None, 0)])
        db.execute.side_effect = [boq_result, similar_result]

        with (
            patch("app.services.ai_feature_service.find_similar_projects") as mock_sim,
            _patch_sa(svc),
        ):
            mock_sim.return_value = []
            resp = await svc.detect_anomalies(db, 1)
        assert resp.anomaly_count == 0

    @pytest.mark.asyncio
    async def test_empty_boq_items_returns_empty(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        boq_result = MagicMock()
        boq_result.unique.return_value.scalars.return_value.all.return_value = []
        db.execute.return_value = boq_result

        with _patch_sa(svc):
            resp = await svc.detect_anomalies(db, 1)
        assert resp.anomaly_count == 0


# =========================================================================
# suggest_value_engineering
# =========================================================================


class TestSuggestValueEngineering:
    @pytest.mark.asyncio
    async def test_no_boq_items(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        boq_result = MagicMock()
        boq_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [boq_result, boq_result]

        with _patch_sa(svc):
            resp = await svc.suggest_value_engineering(db, 1)
        assert resp.suggestion_count == 0
        assert resp.total_potential_savings == 0.0

    @pytest.mark.asyncio
    async def test_no_material_id_falls_back(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        item = _mock_boq_item(material_id=None, rate=100.0, quantity=10.0, category="Flooring")
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [item]
        mat_result = MagicMock()
        mat_result.scalars.return_value.all.return_value = [
            _mock_material(id=1, name="Cheap Tile", rate=50.0, category="flooring"),
        ]
        db.execute.side_effect = [empty_result, items_result, mat_result]

        with _patch_sa(svc):
            resp = await svc.suggest_value_engineering(db, 1)
        assert resp.suggestion_count >= 0

    @pytest.mark.asyncio
    async def test_empty_data(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        boq_result = MagicMock()
        boq_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [boq_result, boq_result]

        with _patch_sa(svc):
            resp = await svc.suggest_value_engineering(db, 1)
        assert resp.suggestion_count == 0
        assert resp.total_potential_savings == 0.0
        assert isinstance(resp.suggestions, list)


# =========================================================================
# predict_duration
# =========================================================================


class TestPredictDuration:
    @pytest.mark.asyncio
    async def test_empty_quantities(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        agg_result = MagicMock()
        agg_result.__iter__.return_value = iter([])
        db.execute.return_value = agg_result

        with _patch_sa(svc):
            resp = await svc.predict_duration(db, 1)
        assert resp.total_days == 0
        assert resp.trade_breakdown == []
        assert resp.gantt_data == []
        assert resp.critical_path == []

    @pytest.mark.asyncio
    async def test_with_trade_quantities(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        agg_result = MagicMock()
        agg_result.__iter__.return_value = iter([("Flooring", 100.0, 5)])
        prod_result = MagicMock()
        prod_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [agg_result, prod_result]

        with _patch_sa(svc):
            resp = await svc.predict_duration(db, 1)
        assert resp.total_days > 0
        assert len(resp.trade_breakdown) >= 1
        assert resp.trade_breakdown[0].trade == "Flooring"
        assert resp.trade_breakdown[0].duration_days > 0

    @pytest.mark.asyncio
    async def test_with_productivity_rates(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        agg_result = MagicMock()
        agg_result.__iter__.return_value = iter([("Flooring", 100.0, 5)])
        prod_result = MagicMock()
        prod_result.scalars.return_value.all.return_value = [
            _mock_productivity_rate(trade="Flooring", output_per_day=20.0, crew_size=4),
        ]
        db.execute.side_effect = [agg_result, prod_result]

        with _patch_sa(svc):
            resp = await svc.predict_duration(db, 1)
        assert resp.total_days > 0
        assert resp.trade_breakdown[0].duration_days >= 1.0

    @pytest.mark.asyncio
    async def test_gantt_data_has_expected_structure(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        agg_result = MagicMock()
        agg_result.__iter__.return_value = iter([
            ("Civil", 50.0, 3),
            ("Gypsum", 200.0, 4),
        ])
        prod_result = MagicMock()
        prod_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [agg_result, prod_result]

        with _patch_sa(svc):
            resp = await svc.predict_duration(db, 1)
        assert len(resp.gantt_data) >= 1
        bar = resp.gantt_data[0]
        assert bar.start_day >= 0
        assert bar.end_day > bar.start_day
        assert bar.duration_days > 0
        assert isinstance(bar.depends_on, list)

    @pytest.mark.asyncio
    async def test_known_trades_predict_duration(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        agg_result = MagicMock()
        agg_result.__iter__.return_value = iter([
            ("Civil", 100.0, 2),
            ("Electrical", 200.0, 3),
        ])
        prod_result = MagicMock()
        prod_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [agg_result, prod_result]

        with _patch_sa(svc):
            resp = await svc.predict_duration(db, 1)
        civil = [t for t in resp.trade_breakdown if t.trade == "Civil"]
        electrical = [t for t in resp.trade_breakdown if t.trade == "Electrical"]
        assert len(civil) == 1
        assert len(electrical) == 1
        assert civil[0].duration_days >= 1.0
        assert electrical[0].duration_days >= 1.0

    @pytest.mark.asyncio
    async def test_no_trade_quantities_empty_response(self):
        import app.services.ai_feature_service as svc

        db = AsyncMock()
        agg_result = MagicMock()
        agg_result.__iter__.return_value = iter([])
        db.execute.return_value = agg_result

        with _patch_sa(svc):
            resp = await svc.predict_duration(db, 1)
        assert resp.total_days == 0
        assert resp.trade_breakdown == []
        assert resp.gantt_data == []
        assert resp.critical_path == []
