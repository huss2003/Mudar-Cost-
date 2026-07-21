"""Unit tests for app.services.rule_engine."""

from __future__ import annotations

import math
import pytest

from app.services.rule_engine import (
    ExpandedLineItem,
    FormulaError,
    WastageRuleCache,
    _infer_material_category,
    _infer_subcategory,
    _tokenize,
    evaluate_formula,
    expand_object,
    expand_detected_objects,
    expand_from_yaml,
)


# =============================================================================
# Formula tokenizer
# =============================================================================


class TestTokenizer:
    def test_simple_numbers(self):
        assert _tokenize("42") == [("NUM", 42.0)]
        assert _tokenize("3.14") == [("NUM", 3.14)]

    def test_number_starting_with_dot(self):
        assert _tokenize(".5") == [("NUM", 0.5)]

    def test_identifiers(self):
        assert _tokenize("L") == [("ID", "L")]
        assert _tokenize("ceil") == [("ID", "ceil")]
        assert _tokenize("var_name") == [("ID", "var_name")]

    def test_operators_and_parens(self):
        tokens = _tokenize("(L+W)*2")
        assert tokens == [
            ("(", "("),
            ("ID", "L"),
            ("+", "+"),
            ("ID", "W"),
            (")", ")"),
            ("*", "*"),
            ("NUM", 2.0),
        ]

    def test_multi_expression(self):
        tokens = _tokenize("ceil(L / 0.6) + 1")
        assert tokens == [
            ("ID", "ceil"),
            ("(", "("),
            ("ID", "L"),
            ("/", "/"),
            ("NUM", 0.6),
            (")", ")"),
            ("+", "+"),
            ("NUM", 1.0),
        ]

    def test_invalid_char(self):
        with pytest.raises(FormulaError, match="Unexpected character"):
            _tokenize("L @ 2")

    def test_lone_decimal(self):
        # A '.' not followed by a digit is an unexpected character
        with pytest.raises(FormulaError, match="Unexpected character"):
            _tokenize("L + .")


# =============================================================================
# Safe formula evaluator
# =============================================================================


class TestEvaluateFormula:
    def test_literal(self):
        assert evaluate_formula("42", {}) == 42.0
        assert evaluate_formula("3.14", {}) == 3.14

    def test_add(self):
        assert evaluate_formula("L + W", {"L": 5, "W": 3}) == 8.0

    def test_sub(self):
        assert evaluate_formula("L - W", {"L": 10, "W": 3}) == 7.0

    def test_mul(self):
        assert evaluate_formula("L * 2", {"L": 4}) == 8.0

    def test_div(self):
        assert evaluate_formula("A / 2", {"A": 10}) == 5.0

    def test_floor_division_not_supported(self):
        """/ is true division, which is fine for our formulas."""
        assert evaluate_formula("5 / 2", {}) == 2.5

    def test_parens(self):
        assert evaluate_formula("(L + W) * 2", {"L": 4, "W": 3}) == 14.0

    def test_operator_precedence(self):
        # multiplication before addition
        assert evaluate_formula("L + W * 2", {"L": 4, "W": 3}) == 10.0
        # parens override
        assert evaluate_formula("(L + W) * 2", {"L": 4, "W": 3}) == 14.0

    def test_unary_minus(self):
        assert evaluate_formula("-L", {"L": 5}) == -5.0
        assert evaluate_formula("--L", {"L": 5}) == 5.0

    def test_ceil_function(self):
        # ceil(L / 0.6) + 1  with L=5000
        # 5000/0.6 = 8333.333..., ceil = 8334, 8334 + 1 = 8335
        result = evaluate_formula("ceil(L / 0.6) + 1", {"L": 5000})
        assert result == 8335.0

    def test_floor_function(self):
        assert evaluate_formula("floor(L / 2)", {"L": 5}) == 2.0

    def test_min_max(self):
        assert evaluate_formula("min(L, W)", {"L": 3, "W": 7}) == 3.0
        assert evaluate_formula("max(L, W)", {"L": 3, "W": 7}) == 7.0

    def test_abs(self):
        assert evaluate_formula("abs(L)", {"L": -5}) == 5.0

    def test_round(self):
        assert evaluate_formula("round(A, 1)", {"A": 3.14159}) == 3.1

    def test_sqrt(self):
        assert evaluate_formula("sqrt(L)", {"L": 9}) == 3.0

    def test_nested_functions(self):
        # ceil(min(L,W) * 2.5)
        result = evaluate_formula("ceil(min(L, W) * 2.5)", {"L": 4, "W": 3})
        # min=3, 3*2.5=7.5, ceil=8
        assert result == 8.0

    def test_multi_level_nested_parens(self):
        # ceil((L + W) * 2 / 0.8)
        result = evaluate_formula(
            "ceil((L + W) * 2 / 0.8)", {"L": 5000, "W": 4000}
        )
        # (5000+4000)*2/0.8 = 9000*2/0.8 = 18000/0.8 = 22500
        assert result == 22500.0

    def test_chain_formulas(self):
        """From boq_rules.yaml examples."""
        # ceiling_hangers = ceil(L/1.2) * ceil(W/1.2)
        # L=6000mm → ceil(6000/1.2) = 5000, W=4800 → ceil(4800/1.2) = 4000
        result = evaluate_formula(
            "ceil(L / 1.2) * ceil(W / 1.2)", {"L": 6000, "W": 4800}
        )
        assert result == 20_000_000.0  # 5000 * 4000

    def test_constant_formula(self):
        """Formulas like '1' or '3' or '4.2'"""
        assert evaluate_formula("1", {}) == 1.0
        assert evaluate_formula("3", {}) == 3.0
        assert evaluate_formula("4.2", {}) == 4.2

    def test_inline_expression_as_formula(self):
        """Formulas like '(2.1 * 2 + 0.9)'"""
        assert evaluate_formula("(2.1 * 2 + 0.9)", {}) == pytest.approx(5.1)

    def test_unknown_variable(self):
        with pytest.raises(FormulaError, match="Unknown variable"):
            evaluate_formula("L + Z", {"L": 10})

    def test_unknown_function(self):
        with pytest.raises(FormulaError, match="Unknown function"):
            evaluate_formula("foo(L)", {"L": 10})

    def test_division_by_zero(self):
        with pytest.raises(FormulaError, match="Division by zero"):
            evaluate_formula("L / 0", {"L": 5})

    def test_empty_formula(self):
        assert evaluate_formula("", {}) == 0.0
        assert evaluate_formula("   ", {}) == 0.0

    def test_power_operator(self):
        result = evaluate_formula("L ** 2", {"L": 4})
        assert result == 16.0

    def test_modulo_operator(self):
        assert evaluate_formula("10 % 3", {}) == 1.0


# =============================================================================
# WastageRuleCache
# =============================================================================


class TestWastageRuleCache:
    def test_empty_cache(self):
        cache = WastageRuleCache()
        assert cache.get_wastage("nope") == 0.0

    def test_exact_match(self):
        rules = [
            {"material_category": "tiling", "material_subcategory": "vitrified_tile",
             "wastage_pct": 8},
        ]
        cache = WastageRuleCache(rules)
        assert cache.get_wastage("tiling", "vitrified_tile") == 8.0

    def test_category_fallback(self):
        rules = [
            {"material_category": "tiling", "material_subcategory": None,
             "wastage_pct": 10},
        ]
        # Note: YAML null becomes None in Python
        cache = WastageRuleCache(rules)
        assert cache.get_wastage("tiling", "vitrified_tile") == 10.0

    def test_no_match_returns_zero(self):
        rules = [
            {"material_category": "tiling", "material_subcategory": "ceramic_tile",
             "wastage_pct": 10},
        ]
        cache = WastageRuleCache(rules)
        assert cache.get_wastage("flooring", "carpet") == 0.0

    def test_subcategory_preferred_over_generic(self):
        rules = [
            {"material_category": "tiling", "material_subcategory": None,
             "wastage_pct": 10},
            {"material_category": "tiling", "material_subcategory": "vitrified_tile",
             "wastage_pct": 8},
        ]
        cache = WastageRuleCache(rules)
        assert cache.get_wastage("tiling", "vitrified_tile") == 8.0

    def test_from_yaml(self):
        """Integration: load the actual wastage_rules.yaml file."""
        import os
        here = os.path.dirname(__file__)
        yaml_path = os.path.join(here, "..", "seed", "rules", "wastage_rules.yaml")
        yaml_path = os.path.normpath(yaml_path)
        cache = WastageRuleCache.from_yaml(yaml_path)
        assert cache.get_wastage("tiling", "vitrified_tile") == 8.0
        assert cache.get_wastage("paint", "interior_emulsion") == 15.0
        assert cache.get_wastage("unknown") == 0.0


# =============================================================================
# Material category inference
# =============================================================================


class TestInferMaterialCategory:
    def test_by_material_code(self):
        assert _infer_material_category("metal_stud_75mm", "", None) == "metal"
        assert _infer_material_category("gypsum_board_12mm", "", None) == "gypsum"
        assert _infer_material_category("carpet", "", None) == "flooring"
        assert _infer_material_category("vitrified_tile", "", None) == "tiling"
        assert _infer_material_category("emulsion_paint", "", None) == "paint"
        assert _infer_material_category("flush_door_35mm", "", None) == "wood"

    def test_fallback_to_trade(self):
        assert _infer_material_category(None, "gypsum_partition", "partition") == "gypsum"
        assert _infer_material_category(None, "false_ceiling", "ceiling") == "gypsum"
        assert _infer_material_category(None, "paint_wall", "painting") == "paint"

    def test_no_match(self):
        assert _infer_material_category("custom_thing", "", "some_trade") == ""

    def test_none_all(self):
        assert _infer_material_category(None, "", None) == ""


# =============================================================================
# Subcategory inference
# =============================================================================


class TestInferSubcategory:
    def test_direct_match(self):
        assert _infer_subcategory("vitrified_tile", "tiling") == "vitrified_tile"
        assert _infer_subcategory("emulsion_paint", "paint") == "interior_emulsion"
        assert _infer_subcategory("tg_glass_12mm", "glass") == "toughened_glass"
        assert _infer_subcategory("gypsum_board_12mm", "gypsum") == "gypsum_board"

    def test_fallback_by_category(self):
        # Generic tile code → falls back to tiling default
        sub = _infer_subcategory("some_tile_unknown", "tiling")
        assert sub == "ceramic_tile"

    def test_none_material_code(self):
        assert _infer_subcategory(None, "painting") is None


# =============================================================================
# expand_object
# =============================================================================


class TestExpandObject:
    """Tests for the main expand_object function."""

    def _gypsum_rule(self) -> dict:
        return {
            "object_type": "gypsum_partition",
            "name": "Gypsum Board Partition",
            "trade": "partition",
            "sub_items": [
                {
                    "material_code": "metal_stud_75mm",
                    "description": "Metal stud 75mm @ 600mm centers",
                    "formula": "ceil(L / 0.6) + 1",
                    "unit": "nos",
                    "default_material": "Metal Stud 75mm",
                    "wastage_pct": 3,
                    "trade": "partition",
                },
                {
                    "material_code": "gypsum_board_12mm",
                    "description": "Gypsum board 12mm (2 layers each side)",
                    "formula": "A * 4",
                    "unit": "sqm",
                    "default_material": "Gypsum Board 12mm",
                    "wastage_pct": 7,
                    "trade": "partition",
                },
                {
                    "material_code": "joint_compound",
                    "description": "Joint compound",
                    "formula": "ceil(A * 0.3)",
                    "unit": "kg",
                    "default_material": "Joint Compound",
                    "wastage_pct": 10,
                    "trade": "partition",
                },
            ],
        }

    def test_basic_expansion(self):
        detected = {
            "object_type": "gypsum_partition",
            "label": "Partition-01",
            "length": 5000.0,
            "height": 3000.0,
            "area": 15.0,
        }
        rule = self._gypsum_rule()
        items = expand_object(detected, rule)

        assert len(items) == 3

        # Item 0: metal studs — formula "ceil(L / 0.6) + 1"
        # L=5000mm → ceil(5000/0.6)=8334, +1=8335
        s0 = items[0]
        assert s0.material_code == "metal_stud_75mm"
        assert s0.description == "Metal stud 75mm @ 600mm centers"
        assert s0.unit == "nos"
        assert s0.quantity == pytest.approx(8335.0)

        # Item 1: gypsum board
        s1 = items[1]
        assert s1.material_code == "gypsum_board_12mm"
        assert s1.quantity == pytest.approx(60.0)  # A=15, 15*4=60
        assert s1.wastage_pct == 7.0
        assert s1.wastage_qty == pytest.approx(60.0 * 7 / 100, rel=1e-9)
        assert s1.total_qty == pytest.approx(60.0 * 1.07, rel=1e-9)

        # Item 2: joint compound
        s2 = items[2]
        assert s2.material_code == "joint_compound"
        assert s2.quantity == pytest.approx(5.0)  # ceil(15*0.3) = ceil(4.5) = 5
        assert s2.wastage_pct == 10.0

    def test_expansion_with_context(self):
        detected = {
            "object_type": "paint_wall",
            "label": "Wall-A",
            "length": 5000.0,
            "width": 4000.0,
            "height": 3000.0,
            "area": 54.0,  # (5+4)*2*3 = 54
        }
        rule = {
            "object_type": "paint_wall",
            "sub_items": [
                {
                    "material_code": "emulsion_paint",
                    "description": "Emulsion paint (2 coats)",
                    "formula": "A * 2",
                    "unit": "sqm",
                    "wastage_pct": 15,
                    "default_material": "Interior Emulsion Paint",
                    "trade": "painting",
                },
            ],
        }
        items = expand_object(detected, rule, context={"room_height": 3.0})
        assert len(items) == 1
        assert items[0].quantity == pytest.approx(108.0)  # 54 * 2

    def test_formula_failure_returns_zero(self):
        detected = {"length": 10, "object_type": "test"}
        rule = {
            "object_type": "test",
            "sub_items": [
                {
                    "material_code": "bad_formula",
                    "description": "Bad formula",
                    "formula": "L + UNKNOWN_VAR",
                    "unit": "nos",
                },
            ],
        }
        items = expand_object(detected, rule)
        assert len(items) == 1
        assert items[0].quantity == 0.0
        assert items[0].formula_used == "L + UNKNOWN_VAR"

    def test_empty_sub_items(self):
        detected = {"object_type": "test", "length": 10}
        rule = {"object_type": "test", "sub_items": []}
        assert expand_object(detected, rule) == []

    def test_provenance_fields(self):
        detected = {"object_type": "wood_door", "id": 42, "label": "Door-A"}
        rule = {
            "object_type": "wood_door",
            "sub_items": [
                {
                    "material_code": "flush_door_35mm",
                    "description": "Flush door",
                    "formula": "1",
                    "unit": "nos",
                },
            ],
        }
        items = expand_object(detected, rule, rule_db_id=7, source_object_id=42)
        assert len(items) == 1
        assert items[0].rule_id == 7
        assert items[0].source_object_id == 42
        assert items[0].source_object_type == "wood_door"
        assert items[0].hierarchy_level == 1

    def test_wastage_lookup_from_cache(self):
        """When sub_item has no wastage_pct, fall back to wastage cache."""
        detected = {
            "object_type": "vitrified_tiles",
            "length": 5000,
            "width": 4000,
            "area": 20.0,
        }
        rule = {
            "object_type": "vitrified_tiles",
            "sub_items": [
                {
                    "material_code": "vitrified_tile",
                    "description": "Vitrified tiles 600x600mm",
                    "formula": "A * 1.08",
                    "unit": "sqm",
                    "default_material": "Vitrified Tile 600x600mm",
                    # NOTE: no wastage_pct → should be looked up
                    "trade": "flooring",
                },
            ],
        }
        wastage_rules = [
            {"material_category": "tiling",
             "material_subcategory": "vitrified_tile",
             "wastage_pct": 8},
        ]
        cache = WastageRuleCache(wastage_rules)
        items = expand_object(detected, rule, wastage_cache=cache)
        assert len(items) == 1
        assert items[0].wastage_pct == 8.0
        assert items[0].quantity == pytest.approx(21.6)  # 20 * 1.08
        assert items[0].wastage_qty == pytest.approx(21.6 * 0.08, rel=1e-9)

    def test_per_item_wastage_overrides_cache(self):
        """Per-sub-item wastage_pct takes priority over cache."""
        detected = {
            "object_type": "test",
            "area": 10.0,
        }
        rule = {
            "object_type": "test",
            "sub_items": [
                {
                    "material_code": "emulsion_paint",
                    "description": "Paint",
                    "formula": "A",
                    "unit": "sqm",
                    "wastage_pct": 5,  # explicit per-item
                    "trade": "painting",
                },
            ],
        }
        cache = WastageRuleCache([
            {"material_category": "paint",
             "material_subcategory": "interior_emulsion",
             "wastage_pct": 15},  # cache says 15%, but per-item says 5%
        ])
        items = expand_object(detected, rule, wastage_cache=cache)
        assert items[0].wastage_pct == 5.0  # per-item wins


# =============================================================================
# expand_detected_objects (batch)
# =============================================================================


class TestExpandDetectedObjects:
    def test_multiple_objects(self):
        detected_list = [
            {"object_type": "wood_door", "id": 1, "label": "Door-1"},
            {"object_type": "wood_door", "id": 2, "label": "Door-2"},
        ]
        rules = [
            {
                "object_type": "wood_door",
                "sub_items": [
                    {
                        "material_code": "flush_door_35mm",
                        "description": "Flush door",
                        "formula": "1",
                        "unit": "nos",
                    },
                ],
            },
        ]
        items = expand_detected_objects(detected_list, rules)
        assert len(items) == 2
        assert items[0].source_object_id == 1
        assert items[1].source_object_id == 2

    def test_unmatched_object_type_skipped(self):
        detected_list = [
            {"object_type": "matched_type", "id": 1, "label": "A"},
            {"object_type": "no_such_rule", "id": 2, "label": "B"},
        ]
        rules = [
            {
                "object_type": "matched_type",
                "sub_items": [
                    {
                        "material_code": "item",
                        "description": "Test item",
                        "formula": "1",
                        "unit": "nos",
                    },
                ],
            },
        ]
        items = expand_detected_objects(detected_list, rules)
        assert len(items) == 1
        assert items[0].source_object_id == 1

    def test_empty_detected_list(self):
        assert expand_detected_objects([], []) == []

    def test_shared_context(self):
        detected_list = [
            {"object_type": "paint_wall", "id": 1, "area": 50.0},
        ]
        rules = [
            {
                "object_type": "paint_wall",
                "sub_items": [
                    {
                        "material_code": "emulsion_paint",
                        "description": "Paint",
                        "formula": "A * coats",
                        "unit": "sqm",
                        "wastage_pct": 0,
                    },
                ],
            },
        ]
        items = expand_detected_objects(
            detected_list, rules, context={"coats": 2},
        )
        assert len(items) == 1
        assert items[0].quantity == pytest.approx(100.0)  # 50 * 2


# =============================================================================
# Integration: expand_from_yaml
# =============================================================================


class TestExpandFromYaml:
    def test_gypsum_partition_expansion(self):
        """End-to-end: load actual YAML rules and expand a gypsum partition."""
        import os
        here = os.path.dirname(__file__)
        backend = os.path.normpath(os.path.join(here, ".."))
        boq_path = os.path.join(backend, "seed", "rules", "boq_rules.yaml")
        wastage_path = os.path.join(backend, "seed", "rules", "wastage_rules.yaml")

        detected_list = [
            {
                "object_type": "gypsum_partition",
                "id": 1,
                "label": "Partition-01",
                "length": 5000.0,
                "width": 100.0,
                "height": 3000.0,
                "area": 15.0,
                "thickness": 100.0,
            },
        ]

        items = expand_from_yaml(
            detected_list,
            boq_rules_path=boq_path,
            wastage_rules_path=wastage_path,
        )

        # gypsum_partition has 12 sub_items (10 material + 2 labour)
        assert len(items) == 12

        # Check a few critical items
        item_map = {i.material_code: i for i in items}

        # Metal studs
        stud = item_map.get("metal_stud_75mm")
        assert stud is not None
        assert stud.unit == "nos"
        assert stud.quantity == pytest.approx(8335.0)  # ceil(5000/0.6)+1
        assert stud.wastage_pct == 3.0  # per-item

        # Gypsum board
        board = item_map.get("gypsum_board_12mm")
        assert board is not None
        assert board.quantity == pytest.approx(60.0)  # 15 * 4
        assert board.wastage_pct == 7.0  # per-item

        # Joint compound (no per-item wastage → should come from cache)
        # Actually joint_compound has wastage_pct: 10 in the YAML
        jc = item_map.get("joint_compound")
        assert jc is not None
        assert jc.quantity == pytest.approx(5.0)  # ceil(15*0.3) = ceil(4.5) = 5
        assert jc.wastage_pct == 10.0

        # Labour items
        pl = item_map.get("partition_labour")
        assert pl is not None
        assert pl.unit == "sqm"
        assert pl.quantity == pytest.approx(15.0)

    def test_vitrified_tiles_wastage_from_cache(self):
        """Tiles have no per-item wastage_pct → should resolve from cache."""
        import os
        here = os.path.dirname(__file__)
        backend = os.path.normpath(os.path.join(here, ".."))
        boq_path = os.path.join(backend, "seed", "rules", "boq_rules.yaml")
        wastage_path = os.path.join(backend, "seed", "rules", "wastage_rules.yaml")

        detected_list = [
            {
                "object_type": "vitrified_tiles",
                "id": 2,
                "label": "Floor-01",
                "length": 5000.0,
                "width": 4000.0,
                "area": 20.0,
            },
        ]

        items = expand_from_yaml(
            detected_list, boq_path, wastage_path,
        )
        item_map = {i.material_code: i for i in items}

        tile = item_map.get("vitrified_tile")
        assert tile is not None
        # vitrified_tile has wastage_pct: 8 in boq_rules.yaml → per-item wins
        assert tile.wastage_pct == 8.0

        # screed_mortar has no per-item wastage → should look up from cache
        screed = item_map.get("screed_mortar")
        assert screed is not None
        # material_category inferred as 'concrete', subcategory 'cement_mortar' → 5%
        assert screed.wastage_pct == 5.0

    def test_unknown_object_type(self):
        """Objects with no matching rule produce no items and a warning."""
        import os
        here = os.path.dirname(__file__)
        backend = os.path.normpath(os.path.join(here, ".."))
        boq_path = os.path.join(backend, "seed", "rules", "boq_rules.yaml")

        items = expand_from_yaml(
            [{"object_type": "unknown_type", "id": 99}],
            boq_rules_path=boq_path,
            wastage_rules_path=None,
        )
        assert items == []


# =============================================================================
# ExpandedLineItem
# =============================================================================


class TestExpandedLineItem:
    def test_default_values(self):
        item = ExpandedLineItem(description="Test")
        assert item.quantity == 0.0
        assert item.unit == "nos"
        assert item.wastage_pct == 0.0
        assert item.wastage_qty == 0.0
        assert item.total_qty == 0.0
        assert item.formula_used is None

    def test_to_dict(self):
        item = ExpandedLineItem(
            description="Test item",
            material_code="test_01",
            quantity=10.0,
            unit="sqm",
            wastage_pct=5.0,
            wastage_qty=0.5,
            total_qty=10.5,
            trade="test",
        )
        d = item.to_dict()
        assert d["description"] == "Test item"
        assert d["quantity"] == 10.0
        assert d["wastage_pct"] == 5.0
        assert d["total_qty"] == 10.5
        assert d["material_name"] is None
