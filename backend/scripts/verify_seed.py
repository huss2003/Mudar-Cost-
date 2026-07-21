#!/usr/bin/env python3
"""
Auto Cost Engine — Seed Data Verification Script

Loads every YAML seed file from seed/ and validates structure, completeness, and
consistency. Exits 0 if all pass, 1 if any fail.

Usage:
    python scripts/verify_seed.py
"""
import sys
from pathlib import Path

# Ensure backend is on the path
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def load_yaml(path):
    """Lazy-import yaml and load the file."""
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def check(condition, message, errors):
    if not condition:
        errors.append(message)
        return False
    return True


def verify_vendors(data):
    """Validate vendors.yaml structure."""
    errors = []
    vendors = data.get("vendors", [])
    codes_seen = set()

    for i, v in enumerate(vendors):
        vid = v.get("id", "")
        name = v.get("name", "?")
        tag = f"vendors[{i}]({name})"

        check(vid, f"{tag}: missing 'id'", errors)
        check(v.get("name"), f"{tag}: missing 'name'", errors)
        check(v.get("vendor_code"), f"{tag}: missing 'vendor_code'", errors)
        check(v.get("gst"), f"{tag}: missing 'gst'", errors)
        gst = v.get("gst", "")
        check(len(gst) == 15, f"{tag}: GST '{gst}' is not 15 characters", errors)
        check(v.get("city"), f"{tag}: missing 'city'", errors)
        check(v.get("state"), f"{tag}: missing 'state'", errors)
        rating = v.get("rating")
        if rating is not None:
            check(0 <= rating <= 5, f"{tag}: rating {rating} out of range [0,5]", errors)

        vcode = v.get("vendor_code")
        if vcode:
            check(vcode not in codes_seen, f"{tag}: duplicate vendor_code '{vcode}'", errors)
            codes_seen.add(vcode)

    return errors


def verify_materials(data, vendor_codes):
    """Validate materials.yaml structure and cross-references."""
    errors = []
    materials = data.get("materials", [])
    skus_seen = set()

    for i, m in enumerate(materials):
        name = m.get("name", "?")
        tag = f"materials[{i}]({name})"

        check(name, f"{tag}: missing 'name'", errors)
        check(m.get("category"), f"{tag}: missing 'category'", errors)
        sku = m.get("sku")
        check(bool(sku), f"{tag}: missing 'sku'", errors)
        if sku:
            check(sku not in skus_seen, f"{tag}: duplicate SKU '{sku}'", errors)
            skus_seen.add(sku)
        hsn = m.get("hsn_code")
        check(bool(hsn), f"{tag}: missing 'hsn_code'", errors)
        if hsn:
            check(len(str(hsn)) == 8, f"{tag}: HSN '{hsn}' should be 8 digits", errors)
        rate = m.get("rate", 0)
        check(rate > 0, f"{tag}: rate {rate} must be positive", errors)
        check(m.get("unit"), f"{tag}: missing 'unit'", errors)
        gst = m.get("gst_rate", 0)
        check(gst in (0, 5, 12, 18, 28), f"{tag}: invalid gst_rate {gst}", errors)
        vr = m.get("vendor_id_ref")
        if vr:
            check(vr in vendor_codes, f"{tag}: vendor_id_ref '{vr}' not found in vendors", errors)

    # Check every vendor has at least one material
    assigned_vendors = {m.get("vendor_id_ref") for m in materials if m.get("vendor_id_ref")}
    for vc in vendor_codes:
        check(vc in assigned_vendors, f"vendor '{vc}' has no materials assigned", errors)

    return errors


def verify_labour(data):
    """Validate labour_rules.yaml structure."""
    errors = []
    rules = data.get("rules", [])

    for i, r in enumerate(rules):
        tag = f"labour[{i}]({r.get('trade', '?')})"
        check(r.get("trade"), f"{tag}: missing 'trade'", errors)
        check(r.get("skill_level"), f"{tag}: missing 'skill_level'", errors)
        check(r.get("unit"), f"{tag}: missing 'unit'", errors)
        check(r.get("total_rate", 0) > 0, f"{tag}: total_rate must be positive", errors)
        check(r.get("basic_rate", 0) > 0, f"{tag}: basic_rate must be positive", errors)

    return errors


def verify_wastage(data):
    """Validate wastage_rules.yaml structure."""
    errors = []
    rules = data.get("rules", [])

    for i, r in enumerate(rules):
        tag = f"wastage[{i}]({r.get('object_type', '?')})"
        check(r.get("object_type"), f"{tag}: missing 'object_type'", errors)
        wp = r.get("wastage_pct")
        check(wp is not None, f"{tag}: missing 'wastage_pct'", errors)
        if wp is not None:
            check(0 <= wp <= 100, f"{tag}: wastage_pct {wp} out of range [0,100]", errors)

    return errors


def verify_productivity(data):
    """Validate productivity_rates.yaml structure."""
    errors = []
    rates = data.get("rates", [])

    for i, r in enumerate(rates):
        tag = f"productivity[{i}]({r.get('trade', '?')})"
        check(r.get("trade"), f"{tag}: missing 'trade'", errors)
        check(r.get("activity"), f"{tag}: missing 'activity'", errors)
        check(r.get("unit"), f"{tag}: missing 'unit'", errors)
        check(r.get("output_per_day", 0) > 0, f"{tag}: output_per_day must be positive", errors)

    return errors


def verify_company_standards(data):
    """Validate company_standards.yaml structure."""
    errors = []
    standards = data.get("standards", [])

    for i, s in enumerate(standards):
        tag = f"standards[{i}]({s.get('category', '?')}:{s.get('name', '?')})"
        check(s.get("category"), f"{tag}: missing 'category'", errors)
        check(s.get("name"), f"{tag}: missing 'name'", errors)

    return errors


VERIFIERS = {
    "reference/vendors.yaml": ("vendors", verify_vendors),
    "reference/materials.yaml": ("materials", verify_materials),
    "rules/labour_rules.yaml": ("rules", verify_labour),
    "rules/wastage_rules.yaml": ("rules", verify_wastage),
    "rules/productivity_rates.yaml": ("rates", verify_productivity),
    "rules/company_standards.yaml": ("standards", verify_company_standards),
}


def main():
    seed_dir = BACKEND / "seed"
    if not seed_dir.exists():
        print(f"ERROR: seed directory not found at {seed_dir}")
        sys.exit(1)

    print("=" * 60)
    print("  Auto Cost Engine — Seed Data Verification")
    print("=" * 60)
    print()

    # Load all YAML files first
    loaded = {}
    all_errors = {}
    total_errors = 0

    for rel_path, (_, _) in VERIFIERS.items():
        path = seed_dir / rel_path
        if not path.exists():
            all_errors[rel_path] = [f"File not found: {path}"]
            total_errors += 1
            continue
        try:
            loaded[rel_path] = load_yaml(path)
        except Exception as e:
            all_errors[rel_path] = [f"Failed to load YAML: {e}"]
            total_errors += 1

    # Extract vendor codes for cross-reference check
    vendor_codes = set()
    if "reference/vendors.yaml" in loaded:
        vendors_data = loaded["reference/vendors.yaml"]
        for v in vendors_data.get("vendors", []):
            vc = v.get("vendor_code")
            if vc:
                vendor_codes.add(vc)

    # Run verifiers
    for rel_path in VERIFIERS:
        if rel_path not in loaded:
            continue
        data = loaded[rel_path]
        key, verifier = VERIFIERS[rel_path]
        # Special case for materials which needs vendor_codes
        if verifier == verify_materials:
            errs = verifier(data, vendor_codes)
        else:
            errs = verifier(data)
        if errs:
            all_errors[rel_path] = errs
            total_errors += len(errs)

    # Print summary table
    summary = []
    for rel_path in sorted(VERIFIERS.keys()):
        path = seed_dir / rel_path
        if not path.exists():
            summary.append((rel_path, "MISSING", "—"))
            continue
        rows = _count_rows(loaded.get(rel_path, {}), VERIFIERS[rel_path][0])
        err_count = len(all_errors.get(rel_path, []))
        status = "FAIL" if err_count else "PASS"
        summary.append((rel_path, rows, status))

    print(f"{'File':<40} {'Rows':<8} {'Status':<6}")
    print("-" * 60)
    for name, rows, status in summary:
        print(f"{name:<40} {str(rows):<8} {status:<6}")
    print("-" * 60)
    print()

    if total_errors:
        print(f"❌  {total_errors} validation error(s) found:\n")
        for rel_path, errs in sorted(all_errors.items()):
            print(f"  {rel_path}:")
            for e in errs:
                print(f"    • {e}")
        print()
        sys.exit(1)
    else:
        print("✅  All seed data validations passed!")
        sys.exit(0)


def _count_rows(data, key):
    if not data:
        return 0
    items = data.get(key, [])
    if isinstance(items, list):
        return len(items)
    return 0


if __name__ == "__main__":
    main()
