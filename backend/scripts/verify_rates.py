#!/usr/bin/env python3
"""
Auto Cost Engine — Rate Mapping Verification Script

Loads rate_mapping.yaml and validates every rate_source reference against:
  - seed/reference/materials.yaml  (for source: material_master)
  - seed/rules/labour_rules.yaml   (for source: labour)

Exits 0 if all references are valid, 1 if any broken links are found.

Usage:
    python scripts/verify_rates.py
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def load_yaml(path):
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def check(condition, message, errors):
    if not condition:
        errors.append(message)
        return False
    return True


def build_material_index(data):
    """Build a dict of sku -> material record."""
    idx = {}
    for m in data.get("materials", []):
        sku = m.get("sku")
        if sku:
            idx[sku] = m
    return idx


def build_labour_index(data):
    """Build a dict of labour_code -> labour rule.

    The labour_code is built as <trade>_<skill_level> from the rule to match
    the labour_code references in rate_mapping.yaml.
    """
    idx = {}
    for r in data.get("rules", []):
        trade = r.get("trade", "")
        skill = r.get("skill_level", "")
        code = f"{trade}_{skill}"
        idx[code] = r
    return idx


def verify_rate_mappings(mappings, materials_idx, labour_idx):
    """Verify every rate_mapping references valid master data."""
    errors = []

    for i, rm in enumerate(mappings):
        obj_type = rm.get("object_type", f"<mapping[{i}]>")
        tag = f"rate_mappings[{i}]({obj_type})"
        source = rm.get("source")

        check(source in ("material_master", "labour"),
              f"{tag}: source must be 'material_master' or 'labour', got '{source}'",
              errors)

        check(rm.get("calibrated_rate") is not None,
              f"{tag}: missing calibrated_rate", errors)

        if source == "material_master":
            mat_code = rm.get("material_code")
            check(bool(mat_code),
                  f"{tag}: missing material_code for material_master source", errors)
            if mat_code:
                check(mat_code in materials_idx,
                      f"{tag}: material_code '{mat_code}' not found in materials.yaml",
                      errors)
                if mat_code in materials_idx:
                    mat = materials_idx[mat_code]
                    master_rate = mat.get("rate")
                    cal_rate = rm.get("calibrated_rate")
                    if master_rate is not None and cal_rate is not None:
                        check(abs(master_rate - cal_rate) < 0.01,
                              f"{tag}: calibrated_rate {cal_rate} != material rate {master_rate} for SKU '{mat_code}'",
                              errors)

        elif source == "labour":
            lab_code = rm.get("labour_code")
            check(bool(lab_code),
                  f"{tag}: missing labour_code for labour source", errors)
            if lab_code:
                check(lab_code in labour_idx,
                      f"{tag}: labour_code '{lab_code}' not found in labour_rules.yaml",
                      errors)
                if lab_code in labour_idx:
                    rule = labour_idx[lab_code]
                    total_rate = rule.get("total_rate")
                    cal_rate = rm.get("calibrated_rate")
                    if total_rate is not None and cal_rate is not None:
                        check(abs(total_rate - cal_rate) < 0.01,
                              f"{tag}: calibrated_rate {cal_rate} != total_rate {total_rate} for labour_code '{lab_code}'",
                              errors)

    return errors


def print_summary_table(mappings, materials_idx, labour_idx):
    """Print a formatted summary table of rate_source -> rate."""
    print()
    print(f"{'Object Type':<30} {'Source':<18} {'Code':<22} {'Rate':<12} {'Status':<8}")
    print("-" * 90)

    for rm in mappings:
        obj_type = rm.get("object_type", "?")
        source = rm.get("source", "?")
        cal_rate = rm.get("calibrated_rate", "?")
        code = "?"

        if source == "material_master":
            code = rm.get("material_code", "?")
            if code in materials_idx:
                status = "✓"
            else:
                status = "✗ BROKEN"
        elif source == "labour":
            code = rm.get("labour_code", "?")
            if code in labour_idx:
                status = "✓"
            else:
                status = "✗ BROKEN"
        else:
            status = "✗ UNKNOWN SOURCE"

        rate_str = f"₹{cal_rate:,.2f}" if isinstance(cal_rate, (int, float)) else str(cal_rate)
        print(f"{obj_type:<30} {source:<18} {code:<22} {rate_str:<12} {status:<8}")

    print("-" * 90)


def main():
    seed_dir = BACKEND / "seed"
    if not seed_dir.exists():
        print(f"ERROR: seed directory not found at {seed_dir}")
        sys.exit(1)

    print("=" * 60)
    print("  Auto Cost Engine — Rate Mapping Verification")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Load all required YAML files
    # ------------------------------------------------------------------
    mapping_path = seed_dir / "rules" / "rate_mapping.yaml"
    materials_path = seed_dir / "reference" / "materials.yaml"
    labour_path = seed_dir / "rules" / "labour_rules.yaml"

    for path, label in [(mapping_path, "rate_mapping.yaml"),
                        (materials_path, "materials.yaml"),
                        (labour_path, "labour_rules.yaml")]:
        if not path.exists():
            print(f"\n❌  {label} not found at {path}")
            sys.exit(1)

    try:
        mapping_data = load_yaml(mapping_path)
        materials_data = load_yaml(materials_path)
        labour_data = load_yaml(labour_path)
    except Exception as e:
        print(f"\n❌  Failed to load YAML: {e}")
        sys.exit(1)

    mappings = mapping_data.get("rate_mappings", [])
    if not mappings:
        print("\n❌  No rate_mappings found in rate_mapping.yaml")
        sys.exit(1)

    materials_idx = build_material_index(materials_data)
    labour_idx = build_labour_index(labour_data)

    print(f"\n  Materials in master:     {len(materials_idx)}")
    print(f"  Labour rules in master:  {len(labour_idx)}")
    print(f"  Rate mappings to verify: {len(mappings)}")

    # ------------------------------------------------------------------
    # Verify each mapping
    # ------------------------------------------------------------------
    errors = verify_rate_mappings(mappings, materials_idx, labour_idx)

    print_summary_table(mappings, materials_idx, labour_idx)

    # ------------------------------------------------------------------
    # Report results
    # ------------------------------------------------------------------
    if errors:
        print(f"\n❌  {len(errors)} verification error(s) found:\n")
        for e in errors:
            print(f"    • {e}")
        print()
        sys.exit(1)
    else:
        print("\n✅  All rate mappings verified! Every rate_source references valid master data.")
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
