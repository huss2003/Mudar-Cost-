"""Unit tests for app.services.drawing_service.

Mocks MinIO client and the database session to test create_drawing,
get_drawing_status, get_drawing_objects, and _map_detected_object.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi import HTTPException, UploadFile

from tests.conftest import _patch_sa


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_upload_file(filename: str = "test.dxf", content: bytes = b"mock_content") -> UploadFile:
    file = MagicMock(spec=UploadFile)
    file.filename = filename
    file.read = AsyncMock(return_value=content)
    return file


def _make_drawing(**kwargs) -> MagicMock:
    d = MagicMock()
    d.id = kwargs.get("id", 1)
    d.filename = kwargs.get("filename", "test.dxf")
    d.file_type = kwargs.get("file_type", "dxf")
    d.minio_object_key = kwargs.get("minio_object_key", "drawings/uuid_test.dxf")
    d.file_size_bytes = kwargs.get("file_size_bytes", 1024)
    d.status = kwargs.get("status", "uploaded")
    d.project_id = kwargs.get("project_id", 1)
    d.error_message = kwargs.get("error_message", None)
    d.created_at = None
    d.processed_at = None
    d.is_deleted = False
    return d


def _make_detected_object(**kwargs) -> MagicMock:
    o = MagicMock()
    o.id = kwargs.get("id", 1)
    o.drawing_id = kwargs.get("drawing_id", 1)
    o.object_type = kwargs.get("object_type", "wall")
    o.label = kwargs.get("label", "Wall-A")
    o.length = kwargs.get("length", 5000.0)
    o.width = kwargs.get("width", None)
    o.area = kwargs.get("area", 15.0)
    o.height = kwargs.get("height", 3000.0)
    o.thickness = kwargs.get("thickness", None)
    o.layer = kwargs.get("layer", "A-WALL")
    o.confidence = kwargs.get("confidence", 0.95)
    o.bbox_coords = kwargs.get("bbox_coords", "[0, 0, 5000, 3000]")
    o.is_deleted = False
    return o


# =========================================================================
# create_drawing
# =========================================================================


@pytest.mark.skip(reason="Requires Postgres+MinIO (docker compose)")
class TestCreateDrawing:
    @pytest.mark.asyncio
    async def test_creates_drawing_successfully(self):
        import app.services.drawing_service as svc

        file = _make_upload_file("floorplan.dxf", b"dxf_content_here")
        with (
            patch("app.services.drawing_service.get_minio_client") as mock_get_minio,
            patch("app.services.drawing_service.async_session") as mock_ctx,
        ):
            mc = MagicMock()
            mock_get_minio.return_value = mc
            db = AsyncMock()
            db.add = MagicMock()
            db.commit = AsyncMock()
            db.refresh = AsyncMock()

            def _refresh_side_effect(instance):
                instance.id = 42

            db.refresh.side_effect = _refresh_side_effect
            cm = AsyncMock()
            cm.__aenter__.return_value = db
            cm.__aexit__.return_value = None
            mock_ctx.return_value = cm

            with _patch_sa(svc, extra={"Drawing": MagicMock()}):
                resp = await svc.create_drawing(file, project_id=1)
            assert resp.drawing_id == 42
            assert resp.filename == "floorplan.dxf"
            assert resp.status == "uploaded"
            assert resp.job_id is None
            mc.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_file_raises_400(self):
        import app.services.drawing_service as svc

        file = _make_upload_file("test.dxf", b"")
        with pytest.raises(HTTPException) as exc:
            await svc.create_drawing(file, project_id=1)
        assert exc.value.status_code == 400
        assert "empty" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invalid_file_extension(self):
        import app.services.drawing_service as svc

        file = _make_upload_file("test.exe", b"content")
        with patch("app.services.drawing_service.validate_upload_file") as mock_val:
            mock_val.return_value = "Invalid file extension"
            with pytest.raises(HTTPException) as exc:
                await svc.create_drawing(file, project_id=1)
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_uploads_dwg(self):
        import app.services.drawing_service as svc

        file = _make_upload_file("drawing.dwg", b"dwg_content")
        with (
            patch("app.services.drawing_service.get_minio_client") as mock_get_minio,
            patch("app.services.drawing_service.async_session") as mock_ctx,
        ):
            mc = MagicMock()
            mock_get_minio.return_value = mc
            db = AsyncMock()
            db.add = MagicMock()
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            cm = AsyncMock()
            cm.__aenter__.return_value = db
            cm.__aexit__.return_value = None
            mock_ctx.return_value = cm
            with _patch_sa(svc, extra={"Drawing": MagicMock()}):
                resp = await svc.create_drawing(file, project_id=1)
            assert resp.drawing_id is not None

    @pytest.mark.asyncio
    async def test_uploads_pdf(self):
        import app.services.drawing_service as svc

        file = _make_upload_file("plan.pdf", b"%PDF-1.4")
        with (
            patch("app.services.drawing_service.get_minio_client") as mock_get_minio,
            patch("app.services.drawing_service.async_session") as mock_ctx,
        ):
            mc = MagicMock()
            mock_get_minio.return_value = mc
            db = AsyncMock()
            db.add = MagicMock()
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            cm = AsyncMock()
            cm.__aenter__.return_value = db
            cm.__aexit__.return_value = None
            mock_ctx.return_value = cm
            with _patch_sa(svc, extra={"Drawing": MagicMock()}):
                resp = await svc.create_drawing(file, project_id=1)
            assert resp.drawing_id is not None


# =========================================================================
# get_drawing_status
# =========================================================================


class TestGetDrawingStatus:
    @pytest.mark.asyncio
    async def test_returns_status(self):
        import app.services.drawing_service as svc

        drawing = _make_drawing(status="processing")
        with patch("app.services.drawing_service.async_session") as mock_ctx:
            db = AsyncMock()
            drawing_result = MagicMock()
            drawing_result.scalar_one_or_none.return_value = drawing
            obj_result = MagicMock()
            obj_result.all.return_value = [(1,), (2,)]
            db.execute.side_effect = [drawing_result, obj_result]
            cm = AsyncMock()
            cm.__aenter__.return_value = db
            cm.__aexit__.return_value = None
            mock_ctx.return_value = cm
            with _patch_sa(svc):
                resp = await svc.get_drawing_status(1)
        assert resp.drawing_id == 1
        assert resp.status == "processing"
        assert resp.object_count == 2

    @pytest.mark.asyncio
    async def test_drawing_not_found(self):
        import app.services.drawing_service as svc

        with patch("app.services.drawing_service.async_session") as mock_ctx:
            db = AsyncMock()
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            db.execute.return_value = result
            cm = AsyncMock()
            cm.__aenter__.return_value = db
            cm.__aexit__.return_value = None
            mock_ctx.return_value = cm
            with _patch_sa(svc):
                with pytest.raises(HTTPException) as exc:
                    await svc.get_drawing_status(999)
            assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_detected_objects(self):
        import app.services.drawing_service as svc

        drawing = _make_drawing(status="completed")
        with patch("app.services.drawing_service.async_session") as mock_ctx:
            db = AsyncMock()
            drawing_result = MagicMock()
            drawing_result.scalar_one_or_none.return_value = drawing
            obj_result = MagicMock()
            obj_result.all.return_value = []
            db.execute.side_effect = [drawing_result, obj_result]
            cm = AsyncMock()
            cm.__aenter__.return_value = db
            cm.__aexit__.return_value = None
            mock_ctx.return_value = cm
            with _patch_sa(svc):
                resp = await svc.get_drawing_status(1)
        assert resp.object_count == 0
        assert resp.status == "completed"


# =========================================================================
# get_drawing_objects
# =========================================================================


class TestGetDrawingObjects:
    @pytest.mark.asyncio
    async def test_returns_objects(self):
        import app.services.drawing_service as svc

        obj = _make_detected_object(id=1, object_type="wall")
        with patch("app.services.drawing_service.async_session") as mock_ctx:
            db = AsyncMock()
            result = MagicMock()
            result.scalars.return_value.all.return_value = [obj]
            db.execute.return_value = result
            cm = AsyncMock()
            cm.__aenter__.return_value = db
            cm.__aexit__.return_value = None
            mock_ctx.return_value = cm
            with _patch_sa(svc):
                objects = await svc.get_drawing_objects(1)
        assert len(objects) == 1
        assert objects[0].id == 1
        assert objects[0].object_type == "wall"


# =========================================================================
# _map_detected_object (pure function)
# =========================================================================


class TestMapDetectedObject:
    def _import_and_test(self):
        import app.services.drawing_service as svc
        return svc

    def test_basic_mapping(self):
        svc = self._import_and_test()
        obj = _make_detected_object(
            id=10, object_type="door", label="Door-1",
            bbox_coords="[100, 200, 1100, 2200]",
        )
        with _patch_sa(svc):
            resp = svc._map_detected_object(obj)
        assert resp.id == 10
        assert resp.object_type == "door"
        assert resp.label == "Door-1"
        assert resp.bbox_coords == [100.0, 200.0, 1100.0, 2200.0]
        assert resp.location_x == 600.0
        assert resp.location_y == 1200.0

    def test_no_bbox(self):
        svc = self._import_and_test()
        obj = _make_detected_object(bbox_coords=None)
        with _patch_sa(svc):
            resp = svc._map_detected_object(obj)
        assert resp.bbox_coords is None
        assert resp.location_x is None
        assert resp.location_y is None

    def test_invalid_bbox_json(self):
        svc = self._import_and_test()
        obj = _make_detected_object(bbox_coords="not json")
        with _patch_sa(svc):
            resp = svc._map_detected_object(obj)
        assert resp.bbox_coords is None

    def test_bbox_too_short(self):
        svc = self._import_and_test()
        obj = _make_detected_object(bbox_coords="[100, 200]")
        with _patch_sa(svc):
            resp = svc._map_detected_object(obj)
        assert resp.bbox_coords == [100.0, 200.0]
        assert resp.location_x is None
        assert resp.location_y is None
