"""Database integrity tests — FK validation, pgvector extension, and schema checks.

These tests require a running PostgreSQL instance with the vector extension.
They are skipped when ``DATABASE_URL`` is not set (offline-friendly).
"""
from __future__ import annotations

import asyncio
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1",
    reason="RUN_DB_TESTS not set to 1 — requires a running PostgreSQL instance",
)


@pytest.fixture(scope="module")
def db_url() -> str:
    """Return the DATABASE_URL from the environment."""
    return os.environ["DATABASE_URL"].replace("+asyncpg", "").replace("+psycopg2", "")


@pytest.mark.asyncio
async def test_foreign_keys_are_valid(db_url: str) -> None:
    """Verify every FK constraint in the public schema is VALID (not NOT VALID).

    PostgreSQL allows constraints to be created with ``NOT VALID``, meaning
    they are *defined* but not *enforced* on existing rows.  This test
    ensures no such constraints exist in the production schema.

    Raises:
        AssertionError: if any FK constraint has ``convalidated = false``.
    """
    import asyncpg

    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            """
            SELECT conname          AS constraint_name,
                   convalidated     AS is_valid,
                   (SELECT rel.relname
                    FROM pg_class rel
                    WHERE rel.oid = conrelid) AS table_name
            FROM pg_constraint
            WHERE contype = 'f'
              AND connamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
              AND convalidated = false
            ORDER BY conname
            """
        )
        invalid = [
            f"{r['table_name']}.{r['constraint_name']}" for r in rows
        ]
        assert not invalid, (
            f"The following {len(invalid)} FK constraint(s) are NOT VALID:\n"
            + "\n".join(f"  - {name}" for name in invalid)
            + "\n\nRun: ALTER TABLE ... VALIDATE CONSTRAINT ... for each."
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_pgvector_extension_installed(db_url: str) -> None:
    """Verify the pgvector extension is installed in the database.

    The ``vector`` extension is required for embedding-based similarity
    search (projects, boq_items).  Without it, ``Vector(384)`` columns
    cannot be created.

    Raises:
        AssertionError: if the vector extension is not installed.
    """
    import asyncpg

    conn = await asyncpg.connect(db_url)
    try:
        row = await conn.fetchrow(
            "SELECT * FROM pg_extension WHERE extname = 'vector'"
        )
        assert row is not None, (
            "pgvector extension is NOT installed.\n"
            "Run: CREATE EXTENSION IF NOT EXISTS vector;\n"
            "Ensure you are using the pgvector/pgvector Docker image "
            "or have pgvector installed on your PostgreSQL server."
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_indexes_exist(db_url: str) -> None:
    """Verify expected performance indexes exist on hot paths.

    This checks for the newly added indexes from migration 0004 and any
    other critical indexes that should always be present.
    """
    import asyncpg

    expected_indexes = {
        # Hot path — FK lookups
        "ix_detected_objects_drawing",
        "ix_drawings_project_id",
        "ix_cost_versions_project",
        "ix_project_history_project",
        "ix_revision_history_project",
        "ix_procurement_project",
        # Composite indexes
        "ix_boq_items_project_trade",
        "ix_cost_versions_project_created",
        "ix_rate_history_reference",
        # Filtering
        "ix_vendors_city",
        "ix_boq_items_category",
        "ix_projects_status",
        "ix_users_email",
        "ix_users_role",
    }

    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            """
            SELECT indexname::text
            FROM pg_indexes
            WHERE schemaname = 'public'
            """
        )
        actual = {r["indexname"] for r in rows}

        missing = expected_indexes - actual
        assert not missing, (
            f"The following {len(missing)} expected index(es) are MISSING:\n"
            + "\n".join(f"  - {name}" for name in sorted(missing))
        )
    finally:
        await conn.close()
