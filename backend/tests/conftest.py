"""Shared fixtures for backend service tests.

All fixtures return mock objects so tests pass offline without
Postgres, MinIO, or any other external service.
"""

from __future__ import annotations

import os

# ── Test env vars (set BEFORE any app code is imported) ────────────
os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "a" * 36)
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://t:t@localhost:5432/t")
os.environ.setdefault("MINIO_ENDPOINT", "minio:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "test")
os.environ.setdefault("MINIO_SECRET_KEY", "test12345678")
os.environ.setdefault("MINIO_BUCKET", "test")
os.environ.setdefault("KEYCLOAK_URL", "http://localhost:8080")
os.environ.setdefault("KEYCLOAK_REALM", "jasfo")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "estimation-web")
os.environ.setdefault("KEYCLOAK_CLIENT_SECRET", "test")
os.environ.setdefault("MIMO_API_KEY", "")
os.environ.setdefault("DEEPSEEK_API_KEY", "")
os.environ.setdefault("CORS_ORIGINS", '["http://localhost:5173"]')


from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock DB Session
# ---------------------------------------------------------------------------


class MockResult:
    """A minimal stand-in for sqlalchemy.engine.Result that supports
    .scalars().all(), .scalar_one_or_none(), .unique(), etc."""

    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def unique(self):
        return self

    def scalar_one_or_none(self):
        return self._scalar

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


@pytest.fixture
def mock_db():
    """Return an AsyncMock that behaves like an async SQLAlchemy session.

    Usage::

        async def test_something(mock_db):
            mock_db.execute.return_value = MockResult(...)
            result = await my_service(mock_db, ...)
    """
    db = AsyncMock()
    db.execute.return_value = MockResult()
    db.get.return_value = None
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def mock_db_session():
    """Patch ``async_session`` context manager so ``async with async_session() as db``
    yields a mock DB."""
    with patch("app.database.async_session") as mock_ctx:
        db = AsyncMock()
        db.execute.return_value = MockResult()
        db.get.return_value = None
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        cm = AsyncMock()
        cm.__aenter__.return_value = db
        cm.__aexit__.return_value = None
        mock_ctx.return_value = cm
        yield db


# ---------------------------------------------------------------------------
# Helper: patch SQLAlchemy ORM functions at the service module level
# to avoid triggering the pre-existing DetectedObject mapper bug.
#
# Usage inside a test function::
#
#     import app.services.material_selector as svc
#     with _patch_sa(svc):
#         result = await svc.get_preferred_brands(db, "tiles")
# ---------------------------------------------------------------------------


def _patch_sa(module, extra=None):
    """Return a context manager that patches ``select`` and optionally
    ``joinedload`` on *module* so they return chainable MagicMock objects.

    *extra* can be a dict of ``{attr_name: mock_value}`` for additional
    module-level attributes to patch (e.g. ``RateHistory`` model classes
    that trigger mapper config on instantiation).

    Usage::

        import app.services.material_selector as svc
        with _patch_sa(svc, extra={'RateHistory': MagicMock()}):
            await svc.select_material(...)
    """
    targets = {
        "select": MagicMock(return_value=MagicMock()),
    }
    # Only patch joinedload if the module actually imports it
    if hasattr(module, "joinedload"):
        targets["joinedload"] = MagicMock(return_value=MagicMock())
    if extra:
        targets.update(extra)
    return patch.multiple(module, **targets)


# ---------------------------------------------------------------------------
# Mock Project / BOQItem / CostVersion (plain data objects)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_project():
    """Return a MagicMock Project instance with typical fields."""
    project = MagicMock()
    project.id = 1
    project.name = "Test Office Fit-Out"
    project.client = "Acme Corp"
    project.project_code = "PROJ-001"
    project.location = "Bangalore"
    project.status = "active"
    project.currency = "INR"
    project.description = "Office fit-out test project"
    project.start_date = None
    project.end_date = None
    project.is_deleted = False
    return project


@pytest.fixture
def mock_boq_item():
    """Return a MagicMock BOQItem with sensible defaults."""
    item = MagicMock()
    item.id = 101
    item.project_id = 1
    item.description = "Vitrified tile flooring"
    item.quantity = 100.0
    item.unit = "sqm"
    item.rate = 850.0
    item.wastage_pct = 10.0
    item.labour_rate = 800.0
    item.transport_rate = 0.0
    item.transport_pct = 0.0
    item.overhead_pct = 10.0
    item.margin_pct = 15.0
    item.discount_pct = 10.0
    item.gst_rate = 18.0
    item.total = 85000.0
    item.category = "Flooring"
    item.material_name = "Vitrified Tile 600x600mm"
    item.material_id = 42
    item.vendor_id = 7
    item.object_id = None
    item.sort_order = 1
    item.is_deleted = False
    item.detected_object = None
    return item


@pytest.fixture
def mock_cost_version():
    """Return a MagicMock CostVersion instance."""
    cv = MagicMock()
    cv.id = 1
    cv.project_id = 1
    cv.name = "v1.0"
    cv.version_number = 1
    cv.status = "draft"
    cv.total_cost = 0.0
    cv.total_materials = 0.0
    cv.total_labour = 0.0
    cv.total_wastage = 0.0
    cv.total_transport = 0.0
    cv.total_overhead = 0.0
    cv.total_margin = 0.0
    cv.grand_total = 0.0
    cv.is_deleted = False
    return cv
