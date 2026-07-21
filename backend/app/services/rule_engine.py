"""
Rule Engine — loads YAML BOQ rules, evaluates formulas against detected object
geometry, applies wastage rules, returns expanded line items.

All formula evaluation is done via a safe recursive-descent parser that never
uses eval() or exec().  Only whitelisted math functions (ceil, floor, min, max,
abs, round, sqrt) are callable.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Shared Data Structures
# =============================================================================


@dataclass
class ExpandedLineItem:
    """A single computed line item from rule expansion."""

    description: str
    material_code: str | None = None
    quantity: float = 0.0
    unit: str = "nos"
    wastage_pct: float = 0.0
    wastage_qty: float = 0.0  # quantity * wastage_pct / 100
    total_qty: float = 0.0  # quantity + wastage_qty
    material_name: str | None = None
    default_rate: float = 0.0
    trade: str | None = None
    rule_id: int | None = None
    source_object_id: int | None = None
    source_object_type: str | None = None
    hierarchy_level: int = 0
    formula_used: str | None = None

    def to_dict(self) -> dict:
        """Return a plain dict (useful for serialisation)."""
        import dataclasses
        return dataclasses.asdict(self)


# =============================================================================
# Safe Formula Evaluator  --  recursive-descent parser (no eval/exec)
# =============================================================================


class FormulaError(ValueError):
    """Raised when a formula cannot be parsed or evaluated."""


def _tokenize(formula: str) -> list[tuple[str, Any]]:
    """Break a formula string into a list of (type, value) tokens."""
    formula = formula.strip()
    tokens: list[tuple[str, Any]] = []
    i = 0
    while i < len(formula):
        ch = formula[i]

        # Whitespace
        if ch.isspace():
            i += 1
            continue

        # Numbers (including decimals)
        if ch.isdigit() or (ch == '.' and i + 1 < len(formula)
                            and formula[i + 1].isdigit()):
            j = i
            dot_count = 0
            while j < len(formula) and (formula[j].isdigit()
                                        or formula[j] == '.'):
                if formula[j] == '.':
                    dot_count += 1
                    if dot_count > 1:
                        break
                j += 1
            # Handle number starting with '.' like '.5'
            token_str = formula[i:j]
            if token_str == '.':
                raise FormulaError(
                    f"Lone decimal point at position {i}")
            tokens.append(('NUM', float(token_str)))
            i = j
            continue

        # Identifiers (variable names / function names)
        if ch.isalpha() or ch == '_':
            j = i
            while j < len(formula) and (formula[j].isalnum()
                                        or formula[j] == '_'):
                j += 1
            tokens.append(('ID', formula[i:j]))
            i = j
            continue

        # Multi-char operators
        if formula[i:i + 2] == '**':
            tokens.append(('**', '**'))
            i += 2
            continue

        # Single-char operators and punctuation
        if ch in '+-*/()%,':
            tokens.append((ch, ch))
            i += 1
            continue

        raise FormulaError(
            f"Unexpected character {ch!r} at position {i}")

    return tokens


class _Parser:
    """
    Recursive-descent parser for safe mathematical expressions.

    Grammar (precedence low → high)::

        expr      → term (('+' | '-') term)*
        term      → factor (('*' | '/' | '%') factor)*
        factor    → ('+' | '-') factor  |  atom ('**' atom)?
        atom      → NUM
                  | ID '(' (expr (',' expr)*)? ')'
                  | '(' expr ')'
                  | ID
    """

    def __init__(self, tokens: list[tuple[str, Any]]):
        self._tokens = tokens
        self._pos = 0

    # -- helpers -----------------------------------------------------------

    def _peek(self) -> tuple[str, Any]:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return ('EOF', None)

    def _advance(self) -> tuple[str, Any]:
        tok = self._peek()
        self._pos += 1
        return tok

    def _expect(self, typ: str, value: Any = None) -> tuple[str, Any]:
        tok = self._peek()
        if tok[0] != typ:
            raise FormulaError(
                f"Expected token type {typ!r}, got {tok[0]!r} ({tok[1]!r})")
        if value is not None and tok[1] != value:
            raise FormulaError(
                f"Expected {value!r}, got {tok[1]!r}")
        return self._advance()

    # -- grammar rules -----------------------------------------------------

    def parse(self, vars_dict: dict[str, float]) -> float:
        self._vars = vars_dict
        result = self._expr()
        if self._pos < len(self._tokens):
            raise FormulaError(
                f"Unexpected token {self._peek()[1]!r} after expression")
        return result

    def _expr(self) -> float:
        left = self._term()
        while self._peek()[0] in ('+', '-'):
            op = self._advance()[1]
            right = self._term()
            if op == '+':
                left = left + right
            else:
                left = left - right
        return left

    def _term(self) -> float:
        left = self._factor()
        while self._peek()[0] in ('*', '/', '%'):
            op = self._advance()[1]
            right = self._factor()
            if op == '*':
                left = left * right
            elif op == '/':
                if right == 0.0:
                    raise FormulaError("Division by zero")
                left = left / right
            else:  # '%'
                if right == 0.0:
                    raise FormulaError("Modulo by zero")
                left = left % right
        return left

    def _factor(self) -> float:
        # Unary + / -
        if self._peek()[0] in ('+', '-'):
            op = self._advance()[1]
            val = self._factor()
            return -val if op == '-' else val

        # Power **
        left = self._atom()
        if self._peek()[0] == '**':
            self._advance()
            right = self._factor()  # right-associative
            left = left ** right
        return left

    def _atom(self) -> float:
        tok = self._peek()

        # Numeric literal
        if tok[0] == 'NUM':
            self._advance()
            return tok[1]

        # Identifier (variable or function call)
        if tok[0] == 'ID':
            name = tok[1]
            self._advance()
            # Function call?
            if self._peek()[0] == '(':
                return self._call_function(name)
            # Variable lookup
            if name in self._vars:
                val = self._vars[name]
                return float(val) if val is not None else 0.0
            raise FormulaError(f"Unknown variable {name!r}")

        # Parenthesised sub-expression
        if tok[0] == '(':
            self._advance()  # '('
            result = self._expr()
            self._expect(')', ')')
            return result

        raise FormulaError(
            f"Unexpected token {tok[1]!r} (type {tok[0]!r})")

    def _call_function(self, name: str) -> float:
        """Parse and evaluate a function call:  name '(' arg (',' arg)* ')'"""
        SAFE_FUNCTIONS: dict[str, Any] = {
            'ceil': math.ceil,
            'floor': math.floor,
            'min': min,
            'max': max,
            'abs': abs,
            'round': round,
            'sqrt': math.sqrt,
        }
        if name not in SAFE_FUNCTIONS:
            raise FormulaError(f"Unknown function {name!r}")

        self._advance()  # '('
        args: list[float] = []
        if self._peek()[0] != ')':
            args.append(self._expr())
            while self._peek()[0] == ',':
                self._advance()  # ','
                args.append(self._expr())
        self._expect(')', ')')

        fn = SAFE_FUNCTIONS[name]
        # round() expects ndigits as int, but all tokens are parsed as float
        if name == 'round' and len(args) >= 2:
            args[1] = int(args[1])
        # ceil/floor expect a single float
        return float(fn(*args))


# Public convenience wrapper
def evaluate_formula(formula: str, vars: dict[str, float]) -> float:
    """Safely evaluate a mathematical formula string.

    Supports: ``+``, ``-``, ``*``, ``/``, ``%``, ``**``, parentheses,
    numeric literals, variables, and the following functions:

    * ``ceil()``, ``floor()``, ``min()``, ``max()``, ``abs()``, ``round()``,
      ``sqrt()``

    Never uses ``eval()`` or ``exec()``.
    """
    formula = formula.strip()
    if not formula:
        return 0.0
    try:
        tokens = _tokenize(formula)
        return _Parser(tokens).parse(vars)
    except FormulaError:
        raise
    except Exception as exc:
        raise FormulaError(
            f"Failed to evaluate formula {formula!r}: {exc}") from exc


# =============================================================================
# Wastage Rule Cache
# =============================================================================


class WastageRuleCache:
    """In-memory cache for wastage rules loaded from YAML.

    Usage::

        cache = WastageRuleCache.from_yaml("seed/rules/wastage_rules.yaml")
        pct = cache.get_wastage("tiling", "vitrified_tile")   # → 8.0
    """

    def __init__(self, rules: list[dict] | None = None):
        self._raw_rules: list[dict] = rules or []
        self._rebuild()

    def _rebuild(self) -> None:
        """Build fast lookup:  category → {subcategory → pct}."""
        lookup: dict[str, dict[str | None, float]] = {}
        for rule in self._raw_rules:
            cat = rule.get('material_category', '')
            sub = rule.get('material_subcategory')
            pct = float(rule.get('wastage_pct', 0))
            if cat not in lookup:
                lookup[cat] = {}
            lookup[cat][sub] = pct
        self._lookup = lookup

    def get_wastage(
        self,
        material_category: str,
        material_subcategory: str | None = None,
    ) -> float:
        """Look up wastage percentage by material category + subcategory.

        Resolution order:
        1. Exact category + exact subcategory match
        2. Exact category match with ``None`` subcategory (fallback)
        3. Return ``0.0`` if not found
        """
        cat_rules = self._lookup.get(material_category, {})
        if material_subcategory is not None and material_subcategory in cat_rules:
            return cat_rules[material_subcategory]
        if None in cat_rules:
            return cat_rules[None]
        return 0.0

    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'WastageRuleCache':
        """Load wastage rules from a YAML file and return a cache instance."""
        import yaml
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        rules = []
        for r in data.get('rules', []):
            # Normalize simple rules (object_type -> material_category)
            if 'object_type' in r and 'material_category' not in r:
                r['material_category'] = r.pop('object_type')
            rules.append(r)
        for r in data.get('detailed', []):
            rules.append(r)
        return cls(rules)


# =============================================================================
# Material Category Heuristic
# =============================================================================

_MATERIAL_CATEGORY_MAP: dict[str, str] = {
    # gypsum / drywall
    'gypsum_board': 'gypsum',
    'gypsum': 'gypsum',
    'drywall': 'gypsum',
    'joint_compound': 'gypsum',
    'joint_tape': 'gypsum',
    'pop_finish': 'gypsum',
    # glass
    'glass': 'glass',
    'tg_glass': 'glass',
    'structural_silicone': 'glass',
    # flooring / carpet
    'carpet': 'flooring',
    'carpet_underlay': 'flooring',
    'carpet_gripper': 'flooring',
    'carpet_adhesive': 'flooring',
    # tiling
    'vitrified_tile': 'tiling',
    'vitrified': 'tiling',
    'tile': 'tiling',
    'tile_adhesive': 'adhesive',
    'tile_grout': 'tiling',
    'screed': 'concrete',
    # paint
    'paint': 'paint',
    'emulsion': 'paint',
    'emulsion_paint': 'paint',
    'primer': 'paint',
    'putty': 'paint',
    'wall_putty': 'paint',
    'wall_primer': 'paint',
    'skimming': 'paint',
    'skim_coat': 'paint',
    'enamel_paint': 'paint',
    'ceiling_primer': 'paint',
    'ceiling_paint': 'paint',
    # electrical
    'conduit': 'electrical',
    'wire': 'electrical',
    'copper_wire': 'electrical',
    'pvc_conduit': 'electrical',
    'switch': 'electrical',
    # metal / studs
    'metal_stud': 'metal',
    'metal': 'metal',
    'stud': 'metal',
    'channel': 'metal',
    'ceiling_grid': 'metal',
    'ceiling_wall_angle': 'metal',
    'ceiling_hangers': 'metal',
    'wall_angle': 'metal',
    't_grid': 'metal',
    # wood / carpentry
    'flush_door': 'wood',
    'door_frame': 'wood',
    'wood': 'wood',
    'timber': 'wood',
    # concrete
    'cement': 'concrete',
    'concrete': 'concrete',
    'mortar': 'concrete',
    'screed_mortar': 'concrete',
    # hardware (minimal wastage, not in wastage db)
    'handle': '',
    'hinge': '',
    'lock': '',
    'stopper': '',
    'screw': '',
    'tape': '',
    'sandpaper': '',
    'masking_tape': '',
}

_TRADE_CATEGORY_MAP: dict[str, str] = {
    'partition': 'gypsum',
    'ceiling': 'gypsum',
    'flooring': 'flooring',
    'painting': 'paint',
    'glass': 'glass',
    'electrical': 'electrical',
    'carpentry': 'wood',
    'civil': 'concrete',
    'metal': 'metal',
}


def _infer_material_category(
    material_code: str | None,
    object_type: str,
    trade: str | None,
) -> str:
    """Heuristic to map a material_code / object_type / trade to a wastage
    category string."""
    if material_code:
        mc_lower = material_code.lower()
        for pattern, cat in _MATERIAL_CATEGORY_MAP.items():
            if pattern in mc_lower:
                return cat
    if trade:
        return _TRADE_CATEGORY_MAP.get(trade.lower(), '')
    return ''


# =============================================================================
# Main Expansion Functions
# =============================================================================


def expand_object(
    detected: dict,
    rule: dict,
    context: dict[str, float] | None = None,
    wastage_cache: WastageRuleCache | None = None,
    source_object_id: int | None = None,
    rule_db_id: int | None = None,
) -> list[ExpandedLineItem]:
    """Expand a single detected object through a BOQ rule into line items.

    Parameters
    ----------
    detected:
        Object data.  Expected keys: ``object_type``, ``label``, ``length``,
        ``width``, ``area``, ``height``, ``thickness``, ``layer``.
    rule:
        BOQ rule from ``boq_rules.yaml``.  Must have ``object_type`` and
        ``sub_items`` (list of sub-item dicts).
    context:
        Extra variables for formula evaluation (e.g. ``room_height``,
        ``wall_count``).
    wastage_cache:
        Cache of wastage rules for material-based lookups.  When omitted only
        per-item ``wastage_pct`` fields are used.
    source_object_id:
        Database ID of the detected object (for provenance tracking).
    rule_db_id:
        Database ID of the BOQ rule (for provenance tracking).

    Returns
    -------
    list[ExpandedLineItem]
    """
    context = context or {}

    # Extract geometry variables — default to 0 when missing
    L = float(detected.get('length') or 0.0)
    W = float(detected.get('width') or 0.0)
    A = float(detected.get('area') or 0.0)
    H = float(detected.get('height') or 0.0)
    T = float(detected.get('thickness') or 0.0)
    N = 1.0  # count per object

    vars_dict: dict[str, float] = {
        'L': L, 'W': W, 'A': A, 'H': H, 'T': T, 'N': N,
    }
    vars_dict.update(context)

    object_type = rule.get('object_type', detected.get('object_type', ''))
    sub_items = rule.get('sub_items', [])

    items: list[ExpandedLineItem] = []

    for idx, sub in enumerate(sub_items):
        formula_str = sub.get('formula', '0')
        description = sub.get('description', '')
        material_code = sub.get('material_code') or sub.get('labour_code')
        unit = sub.get('unit', 'nos')
        trade = sub.get('trade')
        material_name = sub.get('default_material') or sub.get('material_name')

        # 1. Evaluate formula
        try:
            quantity = evaluate_formula(formula_str, vars_dict)
        except FormulaError as exc:
            logger.warning(
                "Formula evaluation failed for sub_item #%d of '%s': %s — %s",
                idx, object_type, formula_str, exc,
            )
            quantity = 0.0

        # 2. Determine wastage percentage
        #    Per-item wastage_pct takes highest priority.
        wastage_pct = float(sub.get('wastage_pct') or 0)

        #    If no per-item wastage was provided, try the wastage rule cache.
        if wastage_pct == 0 and wastage_cache is not None:
            material_category = _infer_material_category(
                material_code, object_type, trade,
            )
            if material_category:
                # material_subcategory can often be derived from material_code
                subcategory = _infer_subcategory(material_code, material_category)
                wastage_pct = wastage_cache.get_wastage(
                    material_category, subcategory,
                )

        # 3. Compute wastage quantities
        wastage_qty = quantity * wastage_pct / 100.0
        total_qty = quantity + wastage_qty

        items.append(ExpandedLineItem(
            description=description,
            material_code=material_code,
            quantity=_round_qty(quantity),
            unit=unit,
            wastage_pct=wastage_pct,
            wastage_qty=_round_qty(wastage_qty),
            total_qty=_round_qty(total_qty),
            material_name=material_name,
            trade=trade,
            rule_id=rule_db_id,
            source_object_id=source_object_id,
            source_object_type=object_type,
            hierarchy_level=1,
            formula_used=formula_str,
        ))

    return items


def _infer_subcategory(
    material_code: str | None,
    material_category: str,
) -> str | None:
    """Derive a material subcategory from the material code for wastage lookup.

    This bridges the naming gap between BOQ sub-item codes
    (e.g. ``vitrified_tile``) and wastage rule subcategories
    (e.g. ``vitrified_tile``).
    """
    if not material_code:
        return None
    mc = material_code.lower()

    # Direct subcategory-to-category mappings
    DIRECT: dict[str, str | None] = {
        'vitrified_tile': 'vitrified_tile',
        'carpet': 'carpet',
        'carpet_tile': 'carpet_tile',
        'toughened_glass': 'toughened_glass',
        'tg_glass': 'toughened_glass',
        'laminated_glass': 'laminated_glass',
        'mirror_glass': 'mirror_glass',
        'interior_emulsion': 'interior_emulsion',
        'emulsion_paint': 'interior_emulsion',
        'enamel_paint': 'enamel_paint',
        'wall_primer': 'primer',
        'ceiling_primer': 'primer',
        'primer': 'primer',
        'wall_putty': 'putty',
        'skim_coat': 'putty',
        'gypsum_board': 'gypsum_board',
        'ceiling_board': 'gypsum_board',
        'pop_finish': 'pop_finish',
        'joint_compound': 'joint_compound',
        'plywood': 'plywood',
        'mdf': 'mdf_board',
        'timber': 'timber',
        'ceramic_tile': 'ceramic_tile',
        'porcelain_tile': 'porcelain_tile',
        'mosaic_tile': 'mosaic_tile',
        'pvc_conduit': 'pvc_conduit',
        'copper_wire': 'copper_wire',
        'tile_adhesive': 'tile_adhesive',
        'silicone': 'silicone_sealant',
        'cement_screed': 'cement_mortar',
        'screed_mortar': 'cement_mortar',
    }
    for pattern, subcat in DIRECT.items():
        if pattern in mc:
            return subcat

    # Generic fallbacks by category
    CAT_FALLBACK: dict[str, str] = {
        'tiling': 'ceramic_tile',
        'flooring': 'carpet',
        'glass': 'toughened_glass',
        'paint': 'interior_emulsion',
        'gypsum': 'gypsum_board',
        'metal': 'ms_steel',
        'wood': 'timber',
        'concrete': 'cement_mortar',
        'electrical': 'pvc_conduit',
        'adhesive': 'tile_adhesive',
    }
    return CAT_FALLBACK.get(material_category)


def _round_qty(value: float, decimals: int = 4) -> float:
    """Round a quantity to *decimals* places (avoid floating-point noise)."""
    return round(value, decimals)


def expand_detected_objects(
    detected_list: list[dict],
    rules: list[dict],
    context: dict[str, float] | None = None,
    wastage_cache: WastageRuleCache | None = None,
) -> list[ExpandedLineItem]:
    """Batch-expand a list of detected objects through matching BOQ rules.

    For each detected object, the function finds the rule whose ``object_type``
    matches and calls :func:`expand_object`.  Objects whose type has no
    matching rule produce a warning log message and are skipped.

    Parameters
    ----------
    detected_list:
        List of detected object dicts.
    rules:
        List of BOQ rule dicts from ``boq_rules.yaml``.
    context:
        Extra context variables passed to every expansion call.
    wastage_cache:
        Shared wastage rule cache.

    Returns
    -------
    list[ExpandedLineItem]
    """
    context = context or {}

    # Build rule lookup index
    rule_index: dict[str, dict] = {}
    for rule in rules:
        ot = rule.get('object_type')
        if ot:
            rule_index[ot] = rule

    all_items: list[ExpandedLineItem] = []
    unmatched: list[str] = []

    for detected in detected_list:
        object_type = detected.get('object_type', '')
        rule = rule_index.get(object_type)

        if not rule:
            unmatched.append(
                f"No matching rule for object_type '{object_type}' "
                f"(label: {detected.get('label', 'N/A')})"
            )
            continue

        items = expand_object(
            detected=detected,
            rule=rule,
            context=context,
            wastage_cache=wastage_cache,
            source_object_id=detected.get('id'),
        )
        all_items.extend(items)

    if unmatched:
        for msg in unmatched:
            logger.warning(msg)

    return all_items


# =============================================================================
# Convenience: load-and-expand pipeline
# =============================================================================


def expand_from_yaml(
    detected_list: list[dict],
    boq_rules_path: str = "seed/rules/boq_rules.yaml",
    wastage_rules_path: str | None = "seed/rules/wastage_rules.yaml",
    context: dict[str, float] | None = None,
) -> list[ExpandedLineItem]:
    """Convenience: load YAML files and run batch expansion in one call.

    Parameters
    ----------
    detected_list:
        List of detected object dicts.
    boq_rules_path:
        Path to the BOQ rules YAML file.
    wastage_rules_path:
        Path to the wastage rules YAML file.  Pass ``None`` to skip wastage
        lookups.
    context:
        Extra context variables.

    Returns
    -------
    list[ExpandedLineItem]
    """
    import yaml

    with open(boq_rules_path, 'r') as f:
        boq_data = yaml.safe_load(f)
    rules = boq_data.get('rules', [])

    wastage_cache: WastageRuleCache | None = None
    if wastage_rules_path:
        wastage_cache = WastageRuleCache.from_yaml(wastage_rules_path)

    return expand_detected_objects(
        detected_list=detected_list,
        rules=rules,
        context=context,
        wastage_cache=wastage_cache,
    )
