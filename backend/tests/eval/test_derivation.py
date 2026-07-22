"""Tests for derivation validation in the training loop eval."""
import sys
from pathlib import Path

# Ensure backend/src is importable
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from tests.eval.eval_full_pipeline import VALID_DERIVATIONS, check_derivation


def test_valid_derivations_set():
    """VALID_DERIVATIONS must contain the expected values."""
    assert "file://formulas" in VALID_DERIVATIONS
    assert "derived_from_geometry" in VALID_DERIVATIONS
    assert "derived_from_density_table" in VALID_DERIVATIONS
    assert "hand_keyed" not in VALID_DERIVATIONS


def test_rejects_hand_keyed():
    """Lines with derivation hand_keyed must be rejected."""
    items = [
        {"description": "Test Item", "derivation": "hand_keyed", "formula_id": "SOME_ID"}
    ]
    errors: list[str] = []
    check_derivation(items, errors)
    # Only the derivation check fires (formula_id is present)
    assert len(errors) == 1
    assert "hand_keyed" in errors[0]
    assert "must be one of" in errors[0]


def test_accepts_derived_from_geometry():
    """Lines with derivation derived_from_geometry must be accepted."""
    items = [
        {
            "description": "Flooring Area",
            "derivation": "derived_from_geometry",
            "formula_id": "T01_I01_FLOORING",
        }
    ]
    errors: list[str] = []
    check_derivation(items, errors)
    assert len(errors) == 0


def test_rejects_missing_formula_id():
    """Lines missing formula_id must be rejected."""
    items = [
        {"description": "Test Line", "derivation": "derived_from_geometry"}
    ]
    errors: list[str] = []
    check_derivation(items, errors)
    assert len(errors) == 1
    assert "formula_id" in errors[0].lower()


def test_rejects_empty_derivation():
    """Lines with empty derivation must be rejected."""
    items = [
        {"description": "Empty Derivation", "derivation": "", "formula_id": ""}
    ]
    errors: list[str] = []
    check_derivation(items, errors)
    assert len(errors) >= 1
    assert "must be one of" in errors[0]


def test_accepts_pipeline_item_with_derivation_dict():
    """Pipeline items (derivation as dict with formula/rule_id) must be accepted."""
    items = [
        {
            "description": "Wall Paint Area",
            "derivation": {
                "formula": "length * height",
                "source_objects": [],
                "rule_id": "T03_WALL_PAINT",
                "rule_description": "Paint area",
            },
        }
    ]
    errors: list[str] = []
    check_derivation(items, errors)
    assert len(errors) == 0


def test_rejects_pipeline_item_missing_rule_id():
    """Pipeline items missing rule_id in derivation dict must be rejected."""
    items = [
        {
            "description": "Bad Item",
            "derivation": {
                "formula": "length * height",
                "source_objects": [],
                "rule_description": "Paint area",
            },
        }
    ]
    errors: list[str] = []
    check_derivation(items, errors)
    assert len(errors) == 1
    assert "rule_id" in errors[0].lower()
