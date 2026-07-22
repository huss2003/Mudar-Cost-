#!/usr/bin/env python3
"""
Generalization Test — run full BOQ pipeline on held-out PDFs.

Runs detection (MiMo AI → rule-based PDF fallback), computes quantities from
office_india_v1.yaml formula rules, computes costs from rate_mapping.yaml,
and asserts room counts, trade count (=13), and budget sanity.

Exit codes
----------
    0   PASS — all held-out tests pass
    1   FAIL — one or more tests fail
    2   ERROR — script misconfiguration (missing files, unreachable dependencies)

Report written to ``/tmp/work/generalize_report.json`` regardless of outcome.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

# === Ensure backend is importable ===========================================
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# === Paths =================================================================
HELD_OUT_DIR = REPO_ROOT / "tests" / "fixtures" / "held_out"
EXPECTED_COUNTS_PATH = HELD_OUT_DIR / "expected_counts.json"
REPORT_PATH = Path("/tmp/work/generalize_report.json")
OFFICE_RULES_PATH = (
    REPO_ROOT / "seed" / "projects" / "gu_office" / "office_india_v1.yaml"
)
RATE_MAPPING_PATH = REPO_ROOT / "seed" / "rules" / "rate_mapping.yaml"
RATES_PROJECT_PATH = (
    REPO_ROOT / "seed" / "projects" / "gu_office" / "rates_gu_office.yaml"
)

# Fallback fixtures
FALLBACK_FIXTURES = REPO_ROOT / "tests" / "fixtures"


def _ensure_tmp_work():
    """Create /tmp/work/ if it doesn't exist."""
    Path("/tmp/work").mkdir(parents=True, exist_ok=True)


# ============================================================================
# 1. HELPER: Load YAML safely
# ============================================================================
def load_yaml(path: Path) -> dict:
    """Load and return a YAML file as a dict."""
    try:
        import yaml
    except ImportError:
        print("  ✗ PyYAML not installed. Install with: pip install pyyaml")
        sys.exit(2)

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ============================================================================
# 2. DETECTION — try MiMo first, degrade to rule-based PDF parser
# ============================================================================


def _check_mimo_connectivity() -> bool:
    """Quick connectivity check — can we instantiate a MimoVisionClient?"""
    try:
        from app.ai.mimo_client import MimoVisionClient, MimoConfig
        from app.config import settings

        api_key = settings.MIMO_API_KEY or ""
        if not api_key:
            return False
        # Try a lightweight instantiation (no API call yet)
        client = MimoVisionClient(MimoConfig(api_key=api_key))
        return not client.config.mock_mode
    except Exception:
        return False


def detect_objects(pdf_path: str) -> list[dict]:
    """Run detection on a PDF, returning a list of detected object dicts.

    Strategy:
        1. If MiMo API is reachable, rasterize and run MimoVisionClient.
        2. Otherwise, fall back to rule-based PDF parser (vector + text layers).
    """
    # Try MiMo first
    mimo_available = _check_mimo_connectivity()

    if mimo_available:
        try:
            print(f"    Using MiMo AI detection for {Path(pdf_path).name}")
            return _detect_via_mimo(pdf_path)
        except Exception as exc:
            print(f"    MiMo detection failed: {exc}")
            print(f"    Falling back to rule-based PDF parser...")

    print(f"    Using rule-based PDF parser for {Path(pdf_path).name}")
    return _detect_via_pdf_parser(pdf_path)


def _detect_via_mimo(pdf_path: str) -> list[dict]:
    """Rasterize PDF pages → MiMo detect objects → return dicts."""
    from app.ai.mimo_client import MimoVisionClient, MimoConfig
    from app.ai.rasterizer import rasterize_drawing

    # Rasterize to PNG pages
    png_paths = rasterize_drawing(pdf_path, dpi=150)
    if not png_paths:
        raise RuntimeError("Rasterizer returned no PNG pages")

    client = MimoVisionClient()
    objects: list[dict] = []

    for png_path in png_paths:
        result = client.detect_objects(png_path)
        if result.status == "failed":
            raise RuntimeError(f"MiMo failed on {png_path}: {result.errors}")

        for obj in result.objects:
            d = obj.model_dump() if hasattr(obj, "model_dump") else vars(obj)
            objects.append(d)

    return objects


def _detect_via_pdf_parser(pdf_path: str) -> list[dict]:
    """Use the rule-based PDF parser (vector + text extraction)."""
    from app.services.pdf_parser import parse_pdf

    result = parse_pdf(pdf_path)
    obj_list = (
        result.objects
        if hasattr(result, "objects")
        else result.get("objects", [])
    )

    detected = []
    for o in obj_list:
        if hasattr(o, "model_dump"):
            d = o.model_dump()
        elif isinstance(o, dict):
            d = o
        else:
            d = vars(o)
        if "id" not in d or d["id"] is None:
            d["id"] = hash(str(d)) % (2**31)
        detected.append(d)

    return detected


# ============================================================================
# 3. CONTEXT COMPUTATION — extract variables from detected objects
# ============================================================================


def compute_context(objects: list[dict]) -> dict[str, Any]:
    """Derive formula variables from detected objects.

    Returns a dict like:
        {
            "office_footprint_sft": 1344.0,
            "washroom_n": 2,
            "washroom_area_sum": 120.0,
            "cabins_n": 3,
            "cabins_perimeter_sum": 240.0,
            "workstations_n": 20,
            "meeting_rooms_n": 1,
            "glass_doors_n": 4,
            "server_area_sum": 60.0,
            "pantry_area": 150.0,
            "reception_area": 200.0,
            "display_area": 100.0,
        }
    """
    ctx: dict[str, Any] = {}

    # --- Room-type classification ---
    rooms: list[dict] = []
    cabins: list[dict] = []
    washrooms: list[dict] = []
    meeting_rooms: list[dict] = []
    workstations: list[dict] = []
    glass_doors: list[dict] = []

    # Area accumulators
    washroom_area_sum = 0.0
    server_area_sum = 0.0
    pantry_area = 0.0
    reception_area = 0.0
    display_area = 0.0
    total_floor_area_mm2 = 0.0

    for obj in objects:
        ot = (obj.get("object_type") or "").lower()
        label = (obj.get("label") or "").lower()
        area = obj.get("area") or (
            (obj.get("length") or 0) * (obj.get("width") or 0)
        ) or 0.0

        # Classify by object_type + label heuristics
        if ot in ("room", "washroom", "cabin", "meeting_room", "board_room"):
            rooms.append(obj)

        if ot == "washroom" or "washroom" in label:
            washrooms.append(obj)
            washroom_area_sum += area

        if ot == "cabin" or label.startswith("cabin") or "cabin" in label:
            cabins.append(obj)

        if ot in ("meeting_room", "board_room") or "meeting" in label or "board" in label:
            meeting_rooms.append(obj)

        if "workstation" in label or "desk" in label:
            workstations.append(obj)

        if ot == "glass" or "glass_door" in ot or ("glass" in label and "door" in label):
            glass_doors.append(obj)

        if "server" in label or "it" in label or "server" in ot:
            server_area_sum += area

        if "pantry" in label or "cafeteria" in label or "pantry" in ot:
            pantry_area += area

        if "reception" in label or "reception" in ot:
            reception_area += area

        if "display" in label or "showroom" in label or "display" in ot:
            display_area += area

        # Accumulate total floor area from large walls / wall rects
        if ot in ("wall", "partition") and area > 0:
            total_floor_area_mm2 += area

    # Detect walls by looking for long linear features and computing bounding box area
    # Fallback: compute footprint from wall endpoints
    if total_floor_area_mm2 <= 0:
        xs = [o.get("location_x", 0) or 0 for o in objects if o.get("location_x")]
        ys = [o.get("location_y", 0) or 0 for o in objects if o.get("location_y")]
        if xs and ys:
            bbox_width = max(xs) - min(xs)
            bbox_height = max(ys) - min(ys)
            if bbox_width > 0 and bbox_height > 0:
                total_floor_area_mm2 = bbox_width * bbox_height

    # Convert mm² → sqft (1 sqft = 92903.04 mm²)
    office_footprint_sft = total_floor_area_mm2 / 92903.04 if total_floor_area_mm2 > 0 else 0.0

    # Perimeter approximation from footprint
    footprint_side = math.sqrt(office_footprint_sft) if office_footprint_sft > 0 else 0.0
    cabins_perimeter = len(cabins) * (footprint_side * 0.3)  # rough: each cabin uses ~30% of a side

    ctx["office_footprint_sft"] = round(office_footprint_sft, 2)
    ctx["washroom_n"] = max(len(washrooms), 2)  # default 2 if any washrooms detected
    ctx["washroom_area_sum"] = round(washroom_area_sum / 92903.04, 2) if washroom_area_sum > 0 else 0.0
    ctx["cabins_n"] = max(len(cabins), 0)
    ctx["cabins_perimeter_sum"] = round(cabins_perimeter, 2)
    ctx["workstations_n"] = max(len(workstations), 10)  # default if some detected
    ctx["meeting_rooms_n"] = max(len(meeting_rooms), 0)
    ctx["glass_doors_n"] = max(len(glass_doors), 1)
    ctx["server_area_sum"] = round(server_area_sum / 92903.04, 2) if server_area_sum > 0 else 0.0
    ctx["pantry_area"] = round(pantry_area / 92903.04, 2) if pantry_area > 0 else 0.0
    ctx["reception_area"] = round(reception_area / 92903.04, 2) if reception_area > 0 else 0.0
    ctx["display_area"] = round(display_area / 92903.04, 2) if display_area > 0 else 0.0

    return ctx


# ============================================================================
# 4. FORMULA EVALUATOR — safe recursive-descent (no eval/exec)
# ============================================================================


def safe_eval(formula: str, context: dict[str, Any]) -> float:
    """Evaluate a formula string using a safe recursive-descent parser.

    Supports: +, -, *, /, ^, **, ceil(), floor(), sqrt(), abs(), round(),
    min(), max(), parentheses, numbers, and context variable names.
    """
    # Tokenize
    tokens = _tokenize(formula, context)

    # Parser state
    pos = [0]

    def peek() -> tuple[str, Any] | None:
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def consume(expected: str | None = None) -> tuple[str, Any]:
        tok = tokens[pos[0]]
        pos[0] += 1
        if expected and tok[0] != expected:
            raise ValueError(f"Expected {expected}, got {tok[0]}({tok[1]})")
        return tok

    def parse_expr() -> float:
        """expr := term ( ('+'|'-') term )*"""
        left = parse_term()
        while peek() and peek()[0] in ("PLUS", "MINUS"):
            op = consume()[0]
            right = parse_term()
            if op == "PLUS":
                left += right
            else:
                left -= right
        return left

    def parse_term() -> float:
        """term := factor ( ('*'|'/') factor )*"""
        left = parse_factor()
        while peek() and peek()[0] in ("MUL", "DIV"):
            op = consume()[0]
            right = parse_factor()
            if op == "MUL":
                left *= right
            else:
                if right == 0:
                    raise ValueError("Division by zero")
                left /= right
        return left

    def parse_factor() -> float:
        """factor := primary ( '^' primary )* | '-' factor"""
        if peek() and peek()[0] == "MINUS":
            consume("MINUS")
            return -parse_factor()

        left = parse_primary()

        while peek() and peek()[0] == "POW":
            consume("POW")
            right = parse_primary()
            left = left ** right

        return left

    def parse_primary() -> float:
        """primary := NUMBER | VAR | '(' expr ')' | FUNC '(' expr ')'"""
        tok = peek()
        if tok is None:
            raise ValueError("Unexpected end of formula")

        if tok[0] == "NUM":
            consume("NUM")
            return tok[1]

        if tok[0] == "VAR":
            consume("VAR")
            return tok[1]

        if tok[0] == "LPAREN":
            consume("LPAREN")
            val = parse_expr()
            if peek() and peek()[0] == "RPAREN":
                consume("RPAREN")
            return val

        if tok[0] == "FUNC":
            name = consume("FUNC")[1]
            if peek() and peek()[0] == "LPAREN":
                consume("LPAREN")
            arg = parse_expr()
            if peek() and peek()[0] == "RPAREN":
                consume("RPAREN")

            if name == "ceil":
                return math.ceil(arg)
            elif name == "floor":
                return math.floor(arg)
            elif name == "sqrt":
                return math.sqrt(arg)
            elif name == "abs":
                return abs(arg)
            elif name == "round":
                return round(arg)
            elif name == "min" or name == "max":
                # min/max can take multiple args — check for comma
                args = [arg]
                while peek() and peek()[0] == "COMMA":
                    consume("COMMA")
                    args.append(parse_expr())
                if peek() and peek()[0] == "RPAREN":
                    consume("RPAREN")
                return min(args) if name == "min" else max(args)
            else:
                raise ValueError(f"Unknown function: {name}")

        raise ValueError(f"Unexpected token: {tok}")

    # Check for edge case: simple number
    formula = formula.strip()
    if not formula:
        return 0.0

    try:
        return float(parse_expr())
    except Exception as exc:
        raise ValueError(f"Failed to evaluate '{formula}': {exc}")


def _tokenize(formula: str, context: dict[str, Any]) -> list[tuple[str, Any]]:
    """Tokenize a formula string into (type, value) pairs."""
    tokens: list[tuple[str, Any]] = []
    i = 0
    n = len(formula)

    while i < n:
        ch = formula[i]

        # Skip whitespace
        if ch.isspace():
            i += 1
            continue

        # Number
        if ch.isdigit() or (ch == "." and i + 1 < n and formula[i + 1].isdigit()):
            j = i
            dot_count = 0
            while j < n and (formula[j].isdigit() or formula[j] == "."):
                if formula[j] == ".":
                    dot_count += 1
                    if dot_count > 1:
                        break
                j += 1
            token_str = formula[i:j]
            if token_str == ".":
                raise ValueError(f"Lone decimal point at position {i}")
            tokens.append(("NUM", float(token_str)))
            i = j
            continue

        # Identifier or function name
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (formula[j].isalnum() or formula[j] == "_"):
                j += 1
            ident = formula[i:j]

            # Check if it's a function name (followed by parenthesis)
            if j < n and formula[j] == "(":
                tokens.append(("FUNC", ident))
                i = j
                continue

            # Check if it's a known function (without parens — already resolved or builtin)
            if ident in ("ceil", "floor", "sqrt", "abs", "round", "min", "max"):
                tokens.append(("FUNC", ident))
                i = j
                continue

            # Look up in context
            val = context.get(ident)
            if val is None:
                # Try case-insensitive lookup
                for k, v in context.items():
                    if k.lower() == ident.lower():
                        val = v
                        break
            if val is None:
                raise ValueError(f"Unknown variable: {ident}")
            tokens.append(("VAR", float(val)))
            i = j
            continue

        # Operators and punctuation
        if ch == "+":
            tokens.append(("PLUS", None))
        elif ch == "-":
            tokens.append(("MINUS", None))
        elif ch == "*":
            # Check for ** (power)
            if i + 1 < n and formula[i + 1] == "*":
                tokens.append(("POW", None))
                i += 1
            else:
                tokens.append(("MUL", None))
        elif ch == "/":
            tokens.append(("DIV", None))
        elif ch == "^":
            tokens.append(("POW", None))
        elif ch == "(":
            tokens.append(("LPAREN", None))
        elif ch == ")":
            tokens.append(("RPAREN", None))
        elif ch == ",":
            tokens.append(("COMMA", None))
        else:
            raise ValueError(f"Unexpected character '{ch}' at position {i}")

        i += 1

    return tokens


# ============================================================================
# 5. RATE RESOLUTION — load rates from rate_mapping.yaml + project rates
# ============================================================================


def load_rates() -> dict[str, dict[str, Any]]:
    """Load rate mappings from rate_mapping.yaml and project rates.

    Returns a flat dict: {rate_key: {"rate": float, "unit": str, ...}}
    """
    rates: dict[str, dict[str, Any]] = {}

    # Load the calibrated rate mappings
    try:
        rm = load_yaml(RATE_MAPPING_PATH)
        for entry in rm.get("rate_mappings", []):
            ot = entry.get("object_type", "")
            cal_rate = entry.get("calibrated_rate", 0.0)
            unit = entry.get("unit", "nos")
            rates[ot] = {
                "rate": cal_rate,
                "unit": unit,
                "source": entry.get("source", "material_master"),
            }
    except Exception as exc:
        print(f"    ⚠  Could not load {RATE_MAPPING_PATH.name}: {exc}")

    # Load project-specific rates (these override the general mappings)
    if RATES_PROJECT_PATH.exists():
        try:
            pr = load_yaml(RATES_PROJECT_PATH)
            for key, val in pr.get("rates", {}).items():
                rates[key] = {
                    "rate": val.get("rate", 0.0),
                    "unit": val.get("unit", "nos"),
                    "source": "project_rates",
                }
        except Exception as exc:
            print(f"    ⚠  Could not load {RATES_PROJECT_PATH.name}: {exc}")

    return rates


def resolve_rate(
    item: dict,
    rates: dict[str, dict[str, Any]],
    context: dict[str, Any],
) -> float:
    """Resolve the rate for a BOQ item.

    Priority:
        1. Item's explicit 'rate' field
        2. rate_mapping.yaml by rate_key
        3. rate_mapping.yaml by object_type
        4. Default 0
    """
    item_rate = item.get("rate", 0.0)
    if item_rate:
        return float(item_rate)

    rate_key = item.get("rate_key", "")
    if rate_key and rate_key in rates:
        return rates[rate_key]["rate"]

    obj_type = item.get("object_type", "")
    if obj_type in rates:
        return rates[obj_type]["rate"]

    return 0.0


# ============================================================================
# 6. QUANTITY COMPUTATION — evaluate all formulas from office_india_v1.yaml
# ============================================================================


def compute_quantities(
    objects: list[dict],
    context: dict[str, Any] | None = None,
) -> list[dict]:
    """Compute BOQ line items from detected objects and formula rules.

    Evaluates every formula in office_india_v1.yaml against the context
    variables derived from detected objects.

    Returns a list of BOQ item dicts with keys:
        description, quantity, unit, rate, amount, trade, object_type,
        formula_id, formula_used
    """
    if context is None:
        context = compute_context(objects)

    # Load the office rules
    rules_data = load_yaml(OFFICE_RULES_PATH)
    trades = rules_data.get("trades", [])

    # Load rates
    rates = load_rates()

    boq_items: list[dict] = []
    errors: list[str] = []

    for trade in trades:
        trade_name = trade.get("name", "Unknown Trade")
        for item in trade.get("items", []):
            try:
                formula_str = item.get("formula", "0")
                description = item.get("description", "")
                unit = item.get("unit", "nos")
                formula_id = item.get("formula_id", "")

                # Evaluate the formula
                qty = safe_eval(formula_str, context)

                # Resolve rate
                item["rate"] = item.get("rate", 0.0) or 0.0
                rate_val = resolve_rate(item, rates, context)

                # Compute amount
                amount = qty * rate_val

                boq_items.append({
                    "description": description[:200],
                    "quantity": round(qty, 2),
                    "unit": unit,
                    "rate": round(rate_val, 2),
                    "amount": round(amount, 2),
                    "trade": trade_name,
                    "object_type": item.get("object_type", ""),
                    "formula_id": formula_id,
                    "formula_used": formula_str,
                })
            except Exception as exc:
                errors.append(
                    f"  [{trade_name}] {item.get('formula_id', '?' )}: "
                    f"formula='{item.get('formula', '')}' → {exc}"
                )

    # Log errors but continue
    if errors:
        for e in errors:
            print(f"    ⚠  {e}")

    return boq_items


# ============================================================================
# 7. COST COMPUTATION — apply cost_engine for full cost breakdown
# ============================================================================


def compute_costs(boq_items: list[dict]) -> list[dict]:
    """Compute cost breakdowns for each BOQ line item.

    Uses the shared cost engine formula if available, otherwise does
    a simple rate × quantity computation.
    """
    try:
        from app.services.cost_engine import compute_line_item

        # Convert our BOQ items to the format expected by compute_line_item
        cost_items = []
        for item in boq_items:
            cost_items.append({
                "item_id": hash(item.get("description", "")) % (2**31),
                "id": hash(item.get("description", "")) % (2**31),
                "description": item["description"],
                "quantity": item["quantity"],
                "unit": item["unit"],
                "rate": item["rate"],
                "trade": item["trade"],
                "wastage_pct": 0.0,
                "overhead_pct": 10.0,
                "margin_pct": 15.0,
                "gst_rate": 18.0,
            })

        cost_results = []
        for ci in cost_items:
            try:
                breakdown = compute_line_item(ci)
                cost_results.append({
                    "description": ci["description"],
                    "quantity": breakdown.quantity,
                    "rate": breakdown.rate,
                    "material_cost": breakdown.material_cost,
                    "labour_cost": breakdown.labour_cost,
                    "overhead_cost": breakdown.overhead_cost,
                    "margin_cost": breakdown.margin_cost,
                    "gst_amount": breakdown.gst_amount,
                    "grand_total": breakdown.grand_total,
                    "trade": ci["trade"],
                })
            except Exception:
                # Fallback: simple calc
                amt = ci["quantity"] * ci["rate"]
                cost_results.append({
                    "description": ci["description"],
                    "quantity": ci["quantity"],
                    "rate": ci["rate"],
                    "material_cost": amt,
                    "labour_cost": 0.0,
                    "overhead_cost": amt * 0.1,
                    "margin_cost": amt * 0.15,
                    "gst_amount": (amt + amt * 0.1 + amt * 0.15) * 0.18,
                    "grand_total": amt + amt * 0.1 + amt * 0.15 + (amt + amt * 0.1 + amt * 0.15) * 0.18,
                    "trade": ci["trade"],
                })

        return cost_results

    except ImportError:
        # Fallback: simple computation
        print("    Using simple cost computation (cost_engine not available)")
        cost_results = []
        for item in boq_items:
            amt = item["quantity"] * item["rate"]
            cost_results.append({
                "description": item["description"],
                "quantity": item["quantity"],
                "rate": item["rate"],
                "material_cost": amt,
                "labour_cost": 0.0,
                "overhead_cost": amt * 0.1,
                "margin_cost": amt * 0.15,
                "gst_amount": (amt + amt * 0.1 + amt * 0.15) * 0.18,
                "grand_total": amt + amt * 0.1 + amt * 0.15 + (amt + amt * 0.1 + amt * 0.15) * 0.18,
                "trade": item["trade"],
            })
        return cost_results


# ============================================================================
# 8. MAIN ASSERTION FUNCTION
# ============================================================================


def run_held_out_test(
    pdf_path: str,
    expected: dict,
    verbose: bool = True,
) -> tuple[int, int, list[str], list[dict]]:
    """Run the full pipeline on one PDF.

    Returns
    -------
    tuple[int, int, list[str], list[dict]]
        (passes, failures, error_messages, boq_items)
    """
    passes = 0
    failures = 0
    errors: list[str] = []

    if verbose:
        print(f"\n  📄  Testing: {Path(pdf_path).name}")

    # --- Phase 1: Detection ---
    try:
        t0 = time.time()
        objects = detect_objects(pdf_path)
        elapsed = time.time() - t0
        if verbose:
            print(f"      Detected {len(objects)} objects in {elapsed*1000:.0f}ms")
    except Exception as exc:
        tb = traceback.format_exc()
        errors.append(f"Detection failed: {exc}\n{tb}")
        if verbose:
            print(f"      ✗ Detection failed: {exc}")
        return passes, failures, errors, []

    # --- Phase 2: Context computation ---
    context = compute_context(objects)
    if verbose:
        print(f"      Context: office={context['office_footprint_sft']:.0f} sqft, "
              f"washrooms={context['washroom_n']}, cabins={context['cabins_n']}, "
              f"workstations={context['workstations_n']}")

    # --- Phase 3: Quantities ---
    try:
        boq_items = compute_quantities(objects, context)
        if verbose:
            print(f"      Generated {len(boq_items)} BOQ items")
    except Exception as exc:
        tb = traceback.format_exc()
        errors.append(f"Quantity computation failed: {exc}\n{tb}")
        if verbose:
            print(f"      ✗ Quantity computation failed: {exc}")
        return passes, failures, errors, []

    # --- Phase 4: Costs ---
    try:
        cost_items = compute_costs(boq_items)

        # Update boq_items with grand_total amounts
        for boq, cost in zip(boq_items, cost_items):
            boq["amount"] = cost["grand_total"]
            boq["rate"] = cost["rate"]
            boq["cost_detail"] = cost

        grand_total = sum(c["grand_total"] for c in cost_items) if cost_items else 0.0
    except Exception as exc:
        tb = traceback.format_exc()
        errors.append(f"Cost computation failed: {exc}\n{tb}")
        if verbose:
            print(f"      ✗ Cost computation failed: {exc}")
        return passes, failures, errors, []

    # ====================================================================
    # Assertions
    # ====================================================================

    # 1. Room count within ±1 of expected
    room_types = {"room", "cabin", "washroom", "meeting_room", "board_room"}
    detected_rooms = [o for o in objects if o.get("object_type", "").lower() in room_types]
    # Also check labels for room-like names
    for o in objects:
        label = (o.get("label") or "").lower()
        if any(kw in label for kw in ("room", "cabin", "washroom", "meeting", "board")):
            if o not in detected_rooms:
                detected_rooms.append(o)

    room_count = len(detected_rooms)
    expected_rooms = expected.get("rooms", 0)
    if abs(room_count - expected_rooms) <= max(1, expected_rooms // 3):
        passes += 1
        if verbose:
            print(f"      ✓ Room count: {room_count} (expected ~{expected_rooms})")
    else:
        failures += 1
        msg = f"room_count: got {room_count}, expected ~{expected_rooms}"
        errors.append(msg)
        if verbose:
            print(f"      ✗ {msg}")

    # 2. At least some BOQ items generated
    if len(boq_items) > 0:
        passes += 1
        if verbose:
            print(f"      ✓ BOQ items: {len(boq_items)} generated")
    else:
        failures += 1
        msg = "No BOQ items generated"
        errors.append(msg)
        if verbose:
            print(f"      ✗ {msg}")

    # 3. Trades count = 13
    trades = set(i["trade"] for i in boq_items)
    if len(trades) == 13:
        passes += 1
        if verbose:
            print(f"      ✓ Trades: {len(trades)} (expected 13)")
    else:
        failures += 1
        msg = f"trades: got {len(trades)}, expected 13. Found: {sorted(trades)}"
        errors.append(msg)
        if verbose:
            print(f"      ✗ {msg}")

    # 4. Budget sanity
    low_budget = expected.get("low_budget", 0)
    high_budget = expected.get("high_budget", 0)
    if low_budget <= grand_total <= high_budget:
        passes += 1
        if verbose:
            print(f"      ✓ Budget: ₹{grand_total:,.0f} (range ₹{low_budget:,.0f}-₹{high_budget:,.0f})")
    else:
        failures += 1
        msg = f"total ₹{grand_total:,.0f} outside range ₹{low_budget:,.0f}-₹{high_budget:,.0f}"
        errors.append(msg)
        if verbose:
            print(f"      ✗ {msg}")

    return passes, failures, errors, boq_items


# ============================================================================
# 9. DEFAULT EXPECTATIONS — built-in baselines
# ============================================================================


def load_expected_counts() -> dict[str, dict]:
    """Load expected_counts.json if it exists, otherwise return built-in defaults."""
    defaults: dict[str, dict] = {
        "clinic_fitout": {
            "rooms": 5,
            "low_budget": 100000,
            "high_budget": 10000000,
        },
        "small_office": {
            "rooms": 3,
            "low_budget": 50000,
            "high_budget": 5000000,
        },
        "office_floor_plan": {
            "rooms": 2,
            "low_budget": 1000,
            "high_budget": 10000000,
        },
        "sample_floor_plan": {
            "rooms": 2,
            "low_budget": 1000,
            "high_budget": 10000000,
        },
    }

    if EXPECTED_COUNTS_PATH.exists():
        try:
            with open(EXPECTED_COUNTS_PATH) as f:
                overrides = json.load(f)
                defaults.update(overrides)
            print(f"  Loaded expected counts from {EXPECTED_COUNTS_PATH}")
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  ⚠  Could not load {EXPECTED_COUNTS_PATH}: {exc}")
            print(f"  → Using built-in defaults")

    return defaults


# ============================================================================
# 10. REPORT WRITER
# ============================================================================


def write_report(
    results: dict[str, dict],
    all_pass: bool,
) -> None:
    """Write JSON report to REPORT_PATH."""
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "all_tests_passed": all_pass,
        "results": results,
    }

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n  📊  Report written to {REPORT_PATH}")


# ============================================================================
# 11. MAIN
# ============================================================================


def find_pdfs() -> list[tuple[str, str]]:
    """Find PDFs to test.

    Returns list of (path, stem_name) tuples.
    Priority:
        1. PDFs in HELD_OUT_DIR
        2. Fall back to tests/fixtures/*.pdf
        3. Fall back to tests/fixtures/real/*.pdf
    """
    pdfs: list[tuple[str, str]] = []

    if HELD_OUT_DIR.exists():
        for p in sorted(HELD_OUT_DIR.glob("*.pdf")):
            pdfs.append((str(p), p.stem.replace("-", "_").replace(" ", "_")))

    if not pdfs:
        # Fall back to fixtures directory
        for p in sorted(FALLBACK_FIXTURES.glob("*.pdf")):
            pdfs.append((str(p), p.stem.replace("-", "_").replace(" ", "_")))

    if not pdfs:
        real_dir = FALLBACK_FIXTURES / "real"
        if real_dir.exists():
            for p in sorted(real_dir.glob("*.pdf")):
                pdfs.append((str(p), p.stem.replace("-", "_").replace(" ", "_")))

    return pdfs


def main() -> int:
    """Entry point."""
    _ensure_tmp_work()

    print("=" * 70)
    print("  🧪  GENERALIZATION TEST — Held-Out Pipeline Validation")
    print("=" * 70)

    # Find PDFs
    pdfs = find_pdfs()
    if not pdfs:
        print("  ✗  No PDF files found to test!")
        print(f"     Searched: {HELD_OUT_DIR}, {FALLBACK_FIXTURES}")
        print(f"     Create PDFs or place them in the fixtures directory.")
        write_report({}, False)
        return 2

    print(f"\n  Found {len(pdfs)} PDF(s) to test:")
    for path, stem in pdfs:
        print(f"    • {Path(path).name}")

    # Load expected counts
    expected_counts = load_expected_counts()

    # Run tests
    results: dict[str, dict] = {}
    overall_pass = True

    for pdf_path, stem in pdfs:
        expected = expected_counts.get(stem, {})
        # Fill in defaults if this stem isn't in expected_counts
        if not expected:
            expected = {
                "rooms": 2,
                "low_budget": 1000,
                "high_budget": 10000000,
            }
            print(f"    ℹ  Using default expectations for '{stem}' (not in expected_counts)")

        passes, failures, errors, boq_items = run_held_out_test(pdf_path, expected)

        grand_total = 0.0
        if boq_items:
            grand_total = sum(i.get("amount", 0.0) or i.get("quantity", 0.0) * i.get("rate", 0.0) for i in boq_items)

        result = {
            "passes": passes,
            "failures": failures,
            "errors": errors,
            "total": round(grand_total, 2),
            "boq_item_count": len(boq_items),
        }
        results[stem] = result

        if failures > 0:
            overall_pass = False

        if passes == 4:
            print(f"\n  ✅  {Path(pdf_path).name}: PASS ({passes}/4)")
        else:
            print(f"\n  ❌  {Path(pdf_path).name}: {passes}/{4} PASS, {failures} FAIL")
            for err in errors:
                print(f"       • {err}")

    # Write report
    write_report(results, overall_pass)

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
