#!/usr/bin/env python3
"""Verify post-migration database state after applying alembic migrations."""
import asyncio
import os
import sys

import asyncpg


async def verify() -> None:
    url = os.environ.get("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db").replace(
        "+asyncpg", ""
    ).replace("+psycopg2", "")
    conn = await asyncpg.connect(url)

    try:
        # Check alembic version
        ver = await conn.fetchrow("SELECT version_num FROM alembic_version")
        if not ver:
            print("FAIL: No alembic_version entry found — migration chain did not apply")
            sys.exit(1)
        print(f"Alembic version: {ver['version_num']}")

        # Check tables exist
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
        tables = [r["tablename"] for r in rows]
        print(f"Tables ({len(tables)}): {tables}")
        assert len(tables) >= 15, f"Expected 15+ tables, found {len(tables)}"

        # Check pgvector extension
        ext = await conn.fetchrow(
            "SELECT * FROM pg_extension WHERE extname = 'vector'"
        )
        if not ext:
            print("FAIL: pgvector extension is NOT installed")
            sys.exit(1)
        print("pgvector: installed")

        # Check indexes exist
        idx_rows = await conn.fetch(
            "SELECT indexname FROM pg_indexes WHERE schemaname='public' ORDER BY indexname"
        )
        print(f"Indexes ({len(idx_rows)}):")
        for r in idx_rows:
            print(f"  - {r['indexname']}")

        # Check FK constraints are valid
        fk_rows = await conn.fetch(
            """
            SELECT conname, convalidated
            FROM pg_constraint
            WHERE contype = 'f'
              AND connamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
              AND convalidated = false
            """
        )
        if fk_rows:
            print(f"FAIL: {len(fk_rows)} FK constraints are NOT VALID:")
            for r in fk_rows:
                print(f"  - {r['conname']}")
            sys.exit(1)
        print("FK constraints: all valid")

        print("\n✓ All migration checks passed")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(verify())
