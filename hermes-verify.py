#!/usr/bin/env python3
"""Quick validation of migration file and CI workflow."""
import json, re, os

ROOT = r"C:\Users\ihp52\auto-cost-engine"

# 1. Migration file
mig = os.path.join(ROOT, "backend", "alembic", "versions", "0004_add_missing_indexes.py")
with open(mig) as f:
    src = f.read()

up_indexes = re.findall(r'op\.create_index\(\s*["\x27]([^"\x27]+)["\x27]', src)
down_indexes = re.findall(r'op\.drop_index\(\s*["\x27]([^"\x27]+)["\x27]', src)

print("=== Migration 0004_add_missing_indexes ===")
print(f"UPGRADE creates: {up_indexes}")
print(f"DOWNGRADE drops: {down_indexes}")

expected_up = {
    "ix_detected_objects_drawing",
    "ix_boq_items_project_trade",
    "ix_cost_versions_project_created",
    "ix_vendors_city",
}
expected_down = {
    "ix_detected_objects_drawing",
    "ix_boq_items_project_trade",
    "ix_cost_versions_project_created",
    "ix_vendors_city",
}

up_ok = expected_up == set(up_indexes)
down_ok = expected_down == set(down_indexes)
print(f"UPGRADE correct: {up_ok}")
print(f"DOWNGRADE correct: {down_ok}")

# Check it doesn't try to create already-existing indexes
bad = {"ix_detected_objects_object_type", "ix_boq_items_category"}
created = set(up_indexes)
overlap = created & bad
print(f"Illegal re-creates: {overlap if overlap else 'NONE'}")

# 2. CI workflow
ci = os.path.join(ROOT, ".github", "workflows", "ci.yml")
with open(ci) as f:
    ci_src = f.read()

print(f"\n=== CI workflow ===")
print(f"migration-check job: {'migration-check:' in ci_src}")
print(f"pgvector image: {'pgvector/pgvector:pg16' in ci_src}")
print(f"alembic downgrade: {'alembic downgrade base' in ci_src}")
print(f"alembic upgrade: {'alembic upgrade head' in ci_src}")
print(f"verify script: {'verify_migration.py' in ci_src}")

# Check needs
needs_match = re.search(r"needs:\s*\[([^\]]+)\]", ci_src)
docker_needs_section = None
for match in re.finditer(r"needs:\s*\[([^\]]+)\]", ci_src):
    if "docker-build" in match.group(1):
        docker_needs_section = match.group(1)
print(f"docker-build needs: {docker_needs_section}")

# 3. Test file
test = os.path.join(ROOT, "backend", "tests", "test_db_integrity.py")
with open(test) as f:
    test_src = f.read()
print(f"\n=== test_db_integrity.py ===")
print(f"skipif: {'skipif' in test_src}")
print(f"async: {'pytest.mark.asyncio' in test_src}")
print(f"FK test: {'test_foreign_keys_are_valid' in test_src}")
print(f"pgvector test: {'test_pgvector_extension_installed' in test_src}")
print(f"indexes test: {'test_indexes_exist' in test_src}")

# 4. Makefile
mk = os.path.join(ROOT, "Makefile")
with open(mk) as f:
    mk_src = f.read()
print(f"\n=== Makefile ===")
print(f"check-migrations: {'check-migrations' in mk_src}")
print(f"check-fks: {'check-fks' in mk_src}")

all_ok = (
    up_ok and down_ok and not overlap
    and "migration-check:" in ci_src
    and "verify_migration.py" in ci_src
    and "check-migrations" in mk_src
    and "check-fks" in mk_src
)
print(f"\n{'='*50}")
print(f"OVERALL: {'PASS' if all_ok else 'FAIL'}")
print(f"{'='*50}")
