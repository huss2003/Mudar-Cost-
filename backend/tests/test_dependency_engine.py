"""Tests for the dependency engine — multi-level BOQ expansion."""

from __future__ import annotations

import pytest

from app.services.rule_engine import (
    ExpandedLineItem,
    FormulaError,
    expand_object,
    evaluate_formula,
)
from app.services.dependency_engine import (
    ExpansionReport,
    _detect_cycles,
    _find_rule,
    _material_code_matches_rule_type,
    expand_with_dependencies,
)


# =========================================================================
# Formula evaluator
# =========================================================================


class TestEvaluateFormula:
    def test_basic_arithmetic(self):
        assert evaluate_formula("L + W", {"L": 3.0, "W": 2.0}) == 5.0
        assert evaluate_formula("L * 2", {"L": 4.0}) == 8.0
        assert evaluate_formula("A / 2", {"A": 10.0}) == 5.0
        assert evaluate_formula("L - W", {"L": 5.0, "W": 3.0}) == 2.0

    def test_ceil_function(self):
        assert evaluate_formula("ceil(L / 0.6)", {"L": 3.0}) == 5.0
        assert evaluate_formula("ceil(3.14)", {}) == 4.0

    def test_floor_function(self):
        assert evaluate_formula("floor(3.9)", {}) == 3.0

    def test_power_and_mod(self):
        assert evaluate_formula("2 ** 3", {}) == 8.0
        assert evaluate_formula("10 % 3", {}) == 1.0

    def test_complex_expression(self):
        # From gypsum_partition: ceil(L / 0.6) + 1 with L=3.0m
        result = evaluate_formula("ceil(L / 0.6) + 1", {"L": 3.0})
        assert result == 6.0  # ceil(3.0/0.6) + 1 = ceil(5.0) + 1 = 6

    def test_area_formula(self):
        # From gypsum_board: A * 4 with A=9sqm
        result = evaluate_formula("A * 4", {"A": 9.0})
        assert result == 36.0

    def test_unknown_variable_raises_error(self):
        """Existing implementation raises FormulaError for unknown vars."""
        with pytest.raises(FormulaError):
            evaluate_formula("X * 2", {"L": 3.0})

    def test_invalid_expression_raises_error(self):
        with pytest.raises((FormulaError, Exception)):
            evaluate_formula("invalid syntax @@", {})

    def test_paint_formula(self):
        # From emulsion_paint: A * 2 * 2
        result = evaluate_formula("A * 2 * 2", {"A": 9.0})
        assert result == 36.0

    def test_perimeter_formula(self):
        # From ceiling_wall_angle: (L + W) * 2
        result = evaluate_formula("(L + W) * 2", {"L": 5.0, "W": 4.0})
        assert result == 18.0

    def test_empty_formula(self):
        assert evaluate_formula("", {}) == 0.0


# =========================================================================
# expand_object
# =========================================================================


GYPSUM_RULE = {
    "object_type": "gypsum_partition",
    "name": "Gypsum Board Partition",
    "trade": "partition",
    "sub_items": [
        {
            "material_code": "metal_stud_75mm",
            "description": "Galvanized metal stud 75mm @ 600mm centers",
            "formula": "ceil(L / 0.6) + 1",
            "unit": "nos",
            "default_material": "Metal Stud 75mm",
            "wastage_pct": 3,
            "trade": "partition",
        },
        {
            "material_code": "gypsum_board_12mm",
            "description": "Gypsum board 12mm (two layers each side)",
            "formula": "A * 4",
            "unit": "sqm",
            "default_material": "Gypsum Board 12mm",
            "wastage_pct": 7,
            "trade": "partition",
        },
        {
            "labour_code": "partition_labour",
            "description": "Partition installation labour",
            "formula": "A",
            "unit": "sqm",
            "trade": "partition",
        },
    ],
}

# NOTE: The existing expand_object uses raw dimension values from the dict.
# The YAML formulas assume L in metres and A in sqm, so we pass values
# already in those units.
DETECTED_WALL = {
    "object_type": "gypsum_partition",
    "length": 3.0,  # meters
    "height": 3.0,  # meters
    "width": 0.1,  # 100mm = 0.1m
    "area": 9.0,  # sqm
}


class TestExpandObject:
    def test_expand_basic(self):
        items = expand_object(DETECTED_WALL, GYPSUM_RULE)
        assert len(items) == 3

    def test_stud_quantity(self):
        items = expand_object(DETECTED_WALL, GYPSUM_RULE)
        stud_item = items[0]
        assert stud_item.material_code == "metal_stud_75mm"
        assert stud_item.unit == "nos"
        # ceil(3.0 / 0.6) + 1 = ceil(5.0) + 1 = 6
        assert stud_item.quantity == 6.0
        assert stud_item.wastage_pct == 3.0
        # wastage_qty = 6 * 0.03 = 0.18
        assert round(stud_item.wastage_qty, 2) == 0.18
        # total_qty = 6 + 0.18
        assert round(stud_item.total_qty, 2) == 6.18

    def test_gypsum_board_quantity(self):
        items = expand_object(DETECTED_WALL, GYPSUM_RULE)
        board_item = items[1]
        assert board_item.material_code == "gypsum_board_12mm"
        assert board_item.quantity == 36.0  # A=9, formula A*4 = 36
        assert board_item.unit == "sqm"
        assert board_item.wastage_pct == 7.0
        assert round(board_item.wastage_qty, 2) == 2.52

    def test_labour_item(self):
        items = expand_object(DETECTED_WALL, GYPSUM_RULE)
        labour_item = items[2]
        assert labour_item.material_code == "partition_labour"
        assert labour_item.quantity == 9.0
        assert labour_item.unit == "sqm"
        assert labour_item.wastage_pct == 0.0

    def test_hierarchy_level_hardcoded(self):
        """Existing expand_object hardcodes hierarchy_level=1."""
        items = expand_object(DETECTED_WALL, GYPSUM_RULE)
        for item in items:
            assert item.hierarchy_level == 1

    def test_source_object_type_carried(self):
        items = expand_object(DETECTED_WALL, GYPSUM_RULE)
        for item in items:
            assert item.source_object_type == "gypsum_partition"

    def test_empty_rule_returns_empty(self):
        items = expand_object(DETECTED_WALL, {})
        assert items == []

    def test_rule_with_no_sub_items(self):
        items = expand_object(DETECTED_WALL, {"object_type": "test", "sub_items": []})
        assert items == []


# =========================================================================
# Rule matching helpers
# =========================================================================


RULES_FOR_MATCHING = [
    {"object_type": "gypsum_partition"},
    {"object_type": "paint_wall"},
    {"object_type": "false_ceiling"},
    {"object_type": "carpet_flooring"},
    {"object_type": "wood_door"},
    {"object_type": "electrical_point"},
]


class TestFindRule:
    def test_exact_match(self):
        rule = _find_rule("gypsum_partition", RULES_FOR_MATCHING)
        assert rule is not None
        assert rule["object_type"] == "gypsum_partition"

    def test_prefix_match_rule_starts_with_query(self):
        # "paint" → "paint_wall"
        rule = _find_rule("paint", RULES_FOR_MATCHING)
        assert rule is not None
        assert rule["object_type"] == "paint_wall"

    def test_prefix_match_query_starts_with_rule(self):
        rules = RULES_FOR_MATCHING + [{"object_type": "door"}]
        # "wood_door" → exact match "wood_door" takes precedence
        rule = _find_rule("wood_door", rules)
        assert rule is not None
        assert rule["object_type"] == "wood_door"

    def test_no_match_returns_none(self):
        rule = _find_rule("nonexistent_type", RULES_FOR_MATCHING)
        assert rule is None

    def test_empty_object_type(self):
        rule = _find_rule("", RULES_FOR_MATCHING)
        assert rule is None

    def test_contains_fallback(self):
        """When prefix fails, contains match works."""
        rules = [{"object_type": "extra_special_type"}]
        rule = _find_rule("special", rules)
        assert rule is not None
        assert rule["object_type"] == "extra_special_type"


class TestMaterialCodeMatchesRuleType:
    def test_exact_match(self):
        rules = [{"object_type": "emulsion_paint"}]
        assert _material_code_matches_rule_type("emulsion_paint", rules) is not None

    def test_no_match(self):
        rules = [{"object_type": "paint_wall"}]
        assert _material_code_matches_rule_type("emulsion_paint", rules) is None

    def test_prefix_match_code_starts_with_type(self):
        rules = [{"object_type": "paint"}]
        assert _material_code_matches_rule_type("paint_wall_master", rules) is not None

    def test_prefix_match_type_starts_with_code(self):
        rules = [{"object_type": "paint_wall"}]
        assert _material_code_matches_rule_type("paint", rules) is not None

    def test_dash_underscore_normalisation(self):
        rules = [{"object_type": "emulsion_paint"}]
        assert _material_code_matches_rule_type("emulsion-paint", rules) is not None

    def test_empty_code_returns_none(self):
        assert _material_code_matches_rule_type("", [{"object_type": "test"}]) is None


# =========================================================================
# Cycle detection (pre-flight)
# =========================================================================


class TestDetectCycles:
    def test_no_cycles(self):
        rules = [
            {
                "object_type": "wall",
                "sub_items": [
                    {"material_code": "brick"},
                    {"material_code": "mortar"},
                ],
            },
            {
                "object_type": "brick",
                "sub_items": [{"material_code": "clay"}],
            },
            {
                "object_type": "mortar",
                "sub_items": [{"material_code": "sand"}],
            },
        ]
        cycles = _detect_cycles(rules)
        assert cycles == []

    def test_self_reference_detected(self):
        rules = [
            {
                "object_type": "wall",
                "sub_items": [{"material_code": "wall"}],
            },
        ]
        cycles = _detect_cycles(rules)
        assert len(cycles) >= 1
        assert ("wall", "wall") in cycles

    def test_mutual_cycle(self):
        rules = [
            {
                "object_type": "a",
                "sub_items": [{"material_code": "b"}],
            },
            {
                "object_type": "b",
                "sub_items": [{"material_code": "a"}],
            },
        ]
        cycles = _detect_cycles(rules)
        assert len(cycles) >= 1
        cycle_pairs = {("a", "b"), ("b", "a")}
        assert any(p in cycle_pairs for p in cycles)

    def test_longer_cycle(self):
        rules = [
            {"object_type": "a", "sub_items": [{"material_code": "b"}]},
            {"object_type": "b", "sub_items": [{"material_code": "c"}]},
            {"object_type": "c", "sub_items": [{"material_code": "a"}]},
        ]
        cycles = _detect_cycles(rules)
        assert len(cycles) >= 1

    def test_cycle_with_unrelated_rules(self):
        rules = [
            {"object_type": "self_loop", "sub_items": [{"material_code": "self_loop"}]},
            {"object_type": "independent", "sub_items": [{"material_code": "stuff"}]},
        ]
        cycles = _detect_cycles(rules)
        assert len(cycles) >= 1
        assert ("self_loop", "self_loop") in cycles

    def test_no_cycles_in_yaml_rules(self):
        """Pre-flight check: actual boq_rules.yaml should have no cycles."""
        import yaml
        from pathlib import Path

        yaml_path = Path(__file__).resolve().parents[1] / "seed" / "rules" / "boq_rules.yaml"
        assert yaml_path.exists(), f"YAML not found at {yaml_path}"
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        rules_list = data.get("rules", [])
        cycles = _detect_cycles(rules_list)
        assert cycles == [], f"Expected no cycles in boq_rules.yaml, got: {cycles}"


# =========================================================================
# expand_with_dependencies — full expansion
# =========================================================================

# Rules that form a dependency chain: gypsum_partition → emulsion_paint → paint_primer
SAMPLE_RULES = [
    {
        "object_type": "gypsum_partition",
        "name": "Gypsum Board Partition",
        "trade": "partition",
        "sub_items": [
            {
                "material_code": "metal_stud_75mm",
                "description": "Metal stud 75mm",
                "formula": "ceil(L / 0.6) + 1",
                "unit": "nos",
                "default_material": "Metal Stud 75mm",
                "wastage_pct": 3,
                "trade": "partition",
            },
            {
                "material_code": "emulsion_paint",
                "description": "Paint finish",
                "formula": "A * 2",
                "unit": "sqm",
                "default_material": "Emulsion Paint",
                "wastage_pct": 10,
                "trade": "painting",
            },
        ],
    },
    {
        "object_type": "emulsion_paint",
        "name": "Emulsion Paint Application",
        "trade": "painting",
        "sub_items": [
            {
                "material_code": "paint_primer",
                "description": "Primer coat",
                "formula": "A",
                "unit": "sqm",
                "default_material": "Primer",
                "wastage_pct": 10,
                "trade": "painting",
            },
            {
                "material_code": "paint_topcoat",
                "description": "Top coat",
                "formula": "A * 2",
                "unit": "sqm",
                "default_material": "Emulsion Top Coat",
                "wastage_pct": 10,
                "trade": "painting",
            },
        ],
    },
    {
        "object_type": "paint_primer",
        "name": "Primer",
        "trade": "painting",
        "sub_items": [
            {
                "material_code": "primer_material",
                "description": "Primer material",
                "formula": "A",
                "unit": "ltr",
                "default_material": "Primer Liquid",
                "wastage_pct": 5,
                "trade": "painting",
            },
        ],
    },
]


class TestExpandWithDependencies:
    def test_single_object_no_dependencies(self):
        """max_depth=0 means only level-0 expansion, no recursion."""
        detected = [
            {
                "object_type": "gypsum_partition",
                "length": 3.0,
                "height": 3.0,
                "area": 9.0,
            },
        ]
        items, report = expand_with_dependencies(detected, SAMPLE_RULES, max_depth=0)
        assert report.total_objects == 1
        assert report.expanded_objects == 1
        assert report.missing_rules == []
        # With max_depth=0, only level-0 items (no recursion)
        assert len(items) == 2  # metal_stud + emulsion_paint
        # All should be hierarchy_level 0
        assert all(i.hierarchy_level == 0 for i in items)

    def test_multi_level(self):
        """Full recursive expansion through three levels."""
        detected = [
            {
                "object_type": "gypsum_partition",
                "length": 3.0,
                "height": 3.0,
                "area": 9.0,
            },
        ]
        items, report = expand_with_dependencies(detected, SAMPLE_RULES, max_depth=5)
        assert report.total_objects == 1
        assert report.expanded_objects == 1

        # Level 0: metal_stud, emulsion_paint
        # Level 1 from emulsion_paint: paint_primer, paint_topcoat
        # Level 2 from paint_primer: primer_material
        # Total: 2 + 2 + 1 = 5
        assert len(items) == 5, f"Expected 5 items, got {len(items)}"

        # Check hierarchy levels
        level0 = [i for i in items if i.hierarchy_level == 0]
        level1 = [i for i in items if i.hierarchy_level == 1]
        level2 = [i for i in items if i.hierarchy_level == 2]
        assert len(level0) == 2
        assert len(level1) == 2
        assert len(level2) == 1

    def test_max_depth_stops_expansion(self):
        """With max_depth=1, only one recursive level should expand."""
        detected = [
            {
                "object_type": "gypsum_partition",
                "length": 3.0,
                "height": 3.0,
                "area": 9.0,
            },
        ]
        items, report = expand_with_dependencies(detected, SAMPLE_RULES, max_depth=1)
        # Level 0: metal_stud, emulsion_paint
        # Level 1 from emulsion_paint: paint_primer, paint_topcoat
        # paint_primer should NOT expand (depth would be 2 > max_depth=1)
        assert len(items) == 4, f"Expected 4 items, got {len(items)}"
        assert report.max_depth_reached == 1

    def test_no_rule_found_adds_missing(self):
        detected = [{"object_type": "unknown_type", "length": 1.0}]
        items, report = expand_with_dependencies(detected, SAMPLE_RULES)
        assert report.total_objects == 1
        assert report.expanded_objects == 0
        assert "unknown_type" in report.missing_rules
        assert items == []

    def test_multiple_same_type(self):
        """Multiple objects of the same type all expand independently."""
        detected = [
            {
                "object_type": "gypsum_partition",
                "length": 3.0,
                "height": 3.0,
                "area": 9.0,
            },
            {
                "object_type": "gypsum_partition",
                "length": 6.0,
                "height": 3.0,
                "area": 18.0,
            },
        ]
        items, report = expand_with_dependencies(detected, SAMPLE_RULES, max_depth=0)
        assert report.total_objects == 2
        assert report.expanded_objects == 2
        # Each expands to 2 → 4 total
        assert len(items) == 4

    def test_mixed_detected_objects(self):
        """Mix of known and unknown types."""
        detected = [
            {
                "object_type": "gypsum_partition",
                "length": 3.0,
                "height": 3.0,
                "area": 9.0,
            },
            {"object_type": "nonexistent"},
        ]
        items, report = expand_with_dependencies(detected, SAMPLE_RULES, max_depth=0)
        assert report.total_objects == 2
        assert report.expanded_objects == 1
        assert "nonexistent" in report.missing_rules
        assert len(items) == 2

    def test_report_cycles_detected(self):
        """Confirm report includes pre-flight cycle info."""
        rules_with_cycle = [
            {"object_type": "a", "sub_items": [{"material_code": "b"}]},
            {"object_type": "b", "sub_items": [{"material_code": "a"}]},
        ]
        detected = [{"object_type": "a", "length": 1.0, "area": 1.0}]
        items, report = expand_with_dependencies(detected, rules_with_cycle, max_depth=5)
        assert len(report.cycles_detected) >= 1

    def test_runtime_cycle_guard(self):
        """A self-referencing rule is caught at runtime."""
        rules = [
            {
                "object_type": "self_ref",
                "sub_items": [
                    {
                        "material_code": "self_ref",
                        "description": "Self reference",
                        "formula": "A",
                        "unit": "sqm",
                        "default_material": "Self",
                        "wastage_pct": 0,
                        "trade": "test",
                    },
                ],
            },
        ]
        detected = [{"object_type": "self_ref", "length": 1.0, "area": 1.0}]
        items, report = expand_with_dependencies(detected, rules, max_depth=10)
        # The first expansion produces 1 item. When trying to recurse, the
        # cycle guard fires and stops further expansion.
        assert len(items) == 1
        assert any("Circular dependency" in e for e in report.errors)

    def test_empty_detected_objects(self):
        items, report = expand_with_dependencies([], SAMPLE_RULES)
        assert items == []
        assert report.total_objects == 0
        assert report.expanded_objects == 0

    def test_max_depth_zero_no_recursion(self):
        """max_depth=0 should never enter child rules."""
        detected = [
            {
                "object_type": "gypsum_partition",
                "length": 3.0,
                "height": 3.0,
                "area": 9.0,
            },
        ]
        items, report = expand_with_dependencies(detected, SAMPLE_RULES, max_depth=0)
        assert len(items) == 2
        assert report.max_depth_reached == 0

    def test_report_counts(self):
        detected = [
            {"object_type": "gypsum_partition", "length": 3.0, "height": 3.0, "area": 9.0},
            {"object_type": "unknown"},
        ]
        items, report = expand_with_dependencies(detected, SAMPLE_RULES, max_depth=5)
        assert report.total_objects == 2
        assert report.expanded_objects == 1
        assert report.missing_rules == ["unknown"]
        assert report.total_line_items == len(items)


# =========================================================================
# ExpansionReport
# =========================================================================


class TestExpansionReport:
    def test_default_values(self):
        report = ExpansionReport()
        assert report.total_objects == 0
        assert report.expanded_objects == 0
        assert report.missing_rules == []
        assert report.total_line_items == 0
        assert report.max_depth_reached == 0
        assert report.cycles_detected == []
        assert report.errors == []

    def test_populated_report(self):
        report = ExpansionReport(
            total_objects=10,
            expanded_objects=8,
            missing_rules=["unknown_a", "unknown_b"],
            total_line_items=42,
            max_depth_reached=3,
            cycles_detected=[("a", "b")],
            errors=["Something went wrong"],
        )
        assert report.total_objects == 10
        assert report.expanded_objects == 8
        assert len(report.missing_rules) == 2
        assert report.max_depth_reached == 3
