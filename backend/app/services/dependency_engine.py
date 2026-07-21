"""Dependency engine: multi-level BOQ expansion with cycle detection.

Features
--------
- Recursively expands detected objects through rule sub-items when a
  sub-item's ``material_code`` matches another rule's ``object_type``.
- Pre-flight static cycle detection via DFS over the rule graph.
- Depth limiting (``max_depth``) to prevent runaway expansion.
- Runtime circular-dependency guard (visited-set per root object).
- Detailed ``ExpansionReport`` with missing-rules tracking.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.services.rule_engine import ExpandedLineItem, expand_object

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class ExpansionReport:
    """Summary of a full BOQ expansion run."""

    total_objects: int = 0
    expanded_objects: int = 0
    missing_rules: list[str] = field(default_factory=list)
    total_line_items: int = 0
    max_depth_reached: int = 0
    cycles_detected: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Rule matching helpers
# ---------------------------------------------------------------------------


def _find_rule(
    object_type: str,
    rules: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Find the best matching rule for *object_type*.

    Priority
    1. Exact match (``object_type == rule["object_type"]``).
    2. Prefix match — rule's object_type starts with the given type
       (e.g. a generic ``"paint"`` query matches ``"paint_wall"`` rule).
    3. Query starts with rule's object_type.
    4. Contains match (fallback).
    """
    if not object_type:
        return None

    # 1. Exact
    for rule in rules:
        if rule.get("object_type") == object_type:
            return rule

    # 2. Rule starts with query (e.g. query="paint" → rule="paint_wall")
    candidates: list[tuple[int, dict[str, Any]]] = []
    for rule in rules:
        rt = rule.get("object_type", "")
        if rt and rt.startswith(object_type):
            candidates.append((len(rt), rule))
    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    # 3. Query starts with rule (e.g. query="paint_wall" → rule="paint")
    candidates = []
    for rule in rules:
        rt = rule.get("object_type", "")
        if rt and object_type.startswith(rt):
            candidates.append((len(rt), rule))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # 4. Contains
    for rule in rules:
        rt = rule.get("object_type", "")
        if rt and (object_type in rt or rt in object_type):
            return rule

    return None


def _material_code_matches_rule_type(
    material_code: str,
    rules: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Check if *material_code* matches any rule's ``object_type``.

    Matching order:
    1. Exact: ``material_code == rule.object_type``
    2. Normalised (dash ↔ underscore)
    3. Rule object_type is a prefix of material_code
    4. Material_code is a prefix of rule object_type
    """
    if not material_code:
        return None

    # 1. Exact
    for rule in rules:
        if rule.get("object_type") == material_code:
            return rule

    # 2. Normalised (dash ↔ underscore)
    normalised = material_code.replace("-", "_")
    for rule in rules:
        if rule.get("object_type", "") == normalised:
            return rule

    # 3. Rule type is a prefix of material code
    for rule in rules:
        rt = rule.get("object_type", "")
        if rt and material_code.startswith(rt):
            return rule

    # 4. Material code is a prefix of rule type
    for rule in rules:
        rt = rule.get("object_type", "")
        if rt and rt.startswith(material_code):
            return rule

    return None


# ---------------------------------------------------------------------------
# Cycle detection (pre-flight, static)
# ---------------------------------------------------------------------------


def _detect_cycles(rules: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Analyse the rule graph for potential cycles before any expansion.

    Builds a directed graph:
        rule.object_type → {material_code values that match other rules}

    Then runs DFS to find back edges.

    Returns
    -------
    list[tuple[str, str]]
        Each tuple is ``(source_object_type, referenced_object_type)``
        representing one edge that participates in a cycle.
    """
    # Build adjacency list: which rules reference other rules via material_code
    type_to_rule: dict[str, dict[str, Any]] = {
        r["object_type"]: r for r in rules if "object_type" in r
    }
    graph: dict[str, set[str]] = defaultdict(set)

    for rule in rules:
        source = rule.get("object_type", "")
        if not source:
            continue
        for sub in rule.get("sub_items", []):
            code = sub.get("material_code") or sub.get("labour_code", "")
            if code and code in type_to_rule:
                graph[source].add(code)

    # DFS colouring: WHITE=0 (unvisited), GRAY=1 (in-progress), BLACK=2 (done)
    WHITE, GRAY, BLACK = 0, 1, 2
    colour: dict[str, int] = defaultdict(lambda: WHITE)
    cycles: list[tuple[str, str]] = []

    def dfs(node: str) -> None:
        colour[node] = GRAY
        for neighbour in graph.get(node, set()):
            if colour[neighbour] == GRAY:
                cycles.append((node, neighbour))
            elif colour[neighbour] == WHITE:
                dfs(neighbour)
        colour[node] = BLACK

    for node in list(graph.keys()):
        if colour[node] == WHITE:
            dfs(node)

    return cycles


# ---------------------------------------------------------------------------
# Main expansion function
# ---------------------------------------------------------------------------


def expand_with_dependencies(
    detected_objects: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    max_depth: int = 5,
    wastage_rules: list[dict[str, Any]] | None = None,
) -> tuple[list[ExpandedLineItem], ExpansionReport]:
    """Multi-level BOQ expansion with circular-dependency protection.

    Algorithm
    ---------
    1. Pre-flight: run static cycle detection (non-blocking, logged only).
    2. For each detected object:
       a. Find the best matching rule (exact → prefix).
       b. If no rule found, add ``object_type`` to ``missing_rules`` and skip.
       c. Call ``expand_object()`` to produce level-0 items.
       d. For each expanded item, check if its ``material_code`` matches
          another rule's ``object_type``.
       e. If yes AND the current depth < ``max_depth``:
          - Create a synthetic detected dict from the item's quantities.
          - Recurse.
       f. Track ``visited`` — a set of ``(object_type, rule_id)`` per root.
          If already visited, skip (cycle guard).
    3. Return a flat list of all items with correct ``hierarchy_level`` and
       an ``ExpansionReport``.

    Parameters
    ----------
    detected_objects : list[dict]
        Detected objects. Each dict should have at least ``object_type``
        and dimension keys (``length``, ``width``, ``height``, ``area``).
    rules : list[dict]
        Rule dictionaries as loaded from ``boq_rules.yaml``. Each must have
        ``object_type`` and ``sub_items``.
    max_depth : int
        Maximum recursion depth (default 5). 0 = no recursive expansion.
    wastage_rules : list[dict] | None
        Not yet applied; reserved for future use.

    Returns
    -------
    tuple[list[ExpandedLineItem], ExpansionReport]
    """
    report = ExpansionReport()
    report.total_objects = len(detected_objects)

    # Pre-flight cycle detection
    try:
        cycles = _detect_cycles(rules)
        report.cycles_detected = cycles
        if cycles:
            logger.warning(
                "Pre-flight cycle detection found %d potential cycles: %s",
                len(cycles),
                cycles,
            )
    except Exception as exc:
        logger.exception("Cycle detection failed: %s", exc)
        report.errors.append(f"Cycle detection error: {exc}")

    # Build lookup: material_code / object_type → rule for O(1) matching
    type_to_rule: dict[str, dict[str, Any]] = {}
    for r in rules:
        ot = r.get("object_type")
        if ot:
            type_to_rule[ot] = r

    all_items: list[ExpandedLineItem] = []

    for detected in detected_objects:
        object_type = detected.get("object_type", "")
        if not object_type:
            report.errors.append("Detected object missing object_type")
            continue

        rule = _find_rule(object_type, rules)
        if rule is None:
            report.missing_rules.append(object_type)
            logger.info("No rule found for object_type=%r", object_type)
            continue

        report.expanded_objects += 1

        # Track visited (object_type, rule_id) per root object
        visited: set[tuple[str, int]] = set()

        # Stack-based DFS: (detected_dict, rule, depth)
        stack: list[tuple[dict[str, Any], dict[str, Any], int]] = [
            (detected, rule, 0),
        ]

        while stack:
            cur_detected, cur_rule, depth = stack.pop()

            # Cycle guard — check visited
            key = (cur_rule.get("object_type", ""), cur_rule.get("id", 0))
            if key in visited:
                logger.warning(
                    "Circular dependency avoided: already expanded "
                    "object_type=%r rule_id=%s (root=%r)",
                    cur_rule.get("object_type"),
                    cur_rule.get("id"),
                    object_type,
                )
                report.errors.append(
                    f"Circular dependency avoided: {cur_rule.get('object_type')}"
                )
                continue
            visited.add(key)

            # Expand this level
            try:
                items = expand_object(
                    detected=cur_detected,
                    rule=cur_rule,
                    source_object_id=cur_detected.get("id"),
                )
            except Exception as exc:
                logger.exception(
                    "expand_object failed for object_type=%r: %s",
                    cur_rule.get("object_type"),
                    exc,
                )
                report.errors.append(
                    f"expand_object({cur_rule.get('object_type')}): {exc}"
                )
                continue

            # The existing expand_object hardcodes hierarchy_level=1 — override
            # to the actual depth in the expansion tree.
            for item in items:
                # Use dataclasses.replace or direct attribute assignment
                object.__setattr__(item, "hierarchy_level", depth)

            # Track max depth
            if depth > report.max_depth_reached:
                report.max_depth_reached = depth

            all_items.extend(items)

            # Check if we should recurse deeper
            if depth < max_depth:
                for item in items:
                    if not item.material_code:
                        continue
                    child_rule = type_to_rule.get(item.material_code)
                    if child_rule is None:
                        child_rule = _material_code_matches_rule_type(
                            item.material_code, rules,
                        )
                    if child_rule is not None:
                        # Build a synthetic "detected" dict so expand_object
                        # can evaluate formulas for the child rule.
                        # The existing expand_object uses L, W, A, H, T, N
                        # vars. We pass the parent item's total_qty as 'A'
                        # (area) so child formulas like "A * 2" work on the
                        # quantity of the parent item.
                        syn_detected: dict[str, Any] = {
                            "object_type": child_rule["object_type"],
                            "id": item.source_object_id,
                            "label": item.description,
                            "length": item.total_qty,
                            "width": 0.0,
                            "height": 0.0,
                            "area": item.total_qty,
                        }
                        stack.append((syn_detected, child_rule, depth + 1))

    report.total_line_items = len(all_items)
    return all_items, report
