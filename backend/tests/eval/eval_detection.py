#!/usr/bin/env python3
"""Eval script: run parsers on fixture files, compare to ground truth, report metrics.

Usage:
    python tests/eval/eval_detection.py
    python tests/eval/eval_detection.py --dxf-only
    python tests/eval/eval_detection.py --pdf-only
    python tests/eval/eval_detection.py --include-ai   # also run AI mock pipeline
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def load_ground_truth() -> dict:
    with open(FIXTURES / "ground_truth.json") as f:
        return json.load(f)


def iou(box_a: list[float], box_b: list[float]) -> float:
    """Intersection-over-Union for two bboxes [x1, y1, x2, y2]."""
    if not box_a or not box_b or len(box_a) < 4 or len(box_b) < 4:
        return 0.0
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    if x1 >= x2 or y1 >= y2:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def match_objects(
    detected: list[dict],
    ground_truth: list[dict],
    iou_threshold: float = 0.2,
) -> dict:
    """Match detected objects to ground truth. Returns per-type metrics."""
    # Build type-specific stats
    stats: dict = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

    # Track which ground truths are matched
    gt_matched = set()
    detected_matched = set()

    # For each detection, find best GT match
    for di, det in enumerate(detected):
        det_type = det.get("object_type", "other")
        det_bbox = det.get("bbox_coords")
        if not det_bbox:
            detected_matched.add(di)
            stats[det_type]["fp"] += 1
            continue

        best_iou = 0
        best_gt = None
        for gi, gt in enumerate(ground_truth):
            if gi in gt_matched:
                continue
            gt_bbox = gt.get("bbox_coords")
            if not gt_bbox:
                continue
            # Type must match for TP
            if gt.get("object_type") != det_type:
                continue
            i = iou(det_bbox, gt_bbox)
            if i > best_iou:
                best_iou = i
                best_gt = gi

        if best_iou >= iou_threshold and best_gt is not None:
            stats[det_type]["tp"] += 1
            gt_matched.add(best_gt)
            detected_matched.add(di)
        else:
            stats[det_type]["fp"] += 1
            detected_matched.add(di)

    # False negatives: unmatched ground truths
    for gi, gt in enumerate(ground_truth):
        if gi not in gt_matched:
            stats[gt["object_type"]]["fn"] += gt.get("count_as", 1)

    return dict(stats)


def print_metrics(stats: dict, title: str):
    """Pretty-print precision/recall/f1 table."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    print(f"  {'Type':<20} {'TP':>4} {'FP':>4} {'FN':>4} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    print(f"  {'-'*60}")

    total_tp = total_fp = total_fn = 0
    for obj_type in sorted(stats.keys()):
        s = stats[obj_type]
        tp, fp, fn = s["tp"], s["fp"], s["fn"]
        total_tp += tp
        total_fp += fp
        total_fn += fn
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        print(f"  {obj_type:<20} {tp:>4} {fp:>4} {fn:>4} {prec:>10.3f} {rec:>10.3f} {f1:>10.3f}")

    print(f"  {'-'*60}")
    prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    print(f"  {'TOTAL':<20} {total_tp:>4} {total_fp:>4} {total_fn:>4} {prec:>10.3f} {rec:>10.3f} {f1:>10.3f}")
    print()


def run_dxf_eval(ground_truth: dict) -> dict:
    """Run DXF parser on sample fixture and evaluate."""
    from app.services.dxf_parser import parse_dxf

    dxf_path = FIXTURES / "sample_floor_plan.dxf"
    if not dxf_path.exists():
        print("  ⚠  DXF fixture not found — skipping")
        return {}

    print(f"\n  Parsing: {dxf_path.name}")
    t0 = time.time()
    result = parse_dxf(str(dxf_path))
    elapsed = time.time() - t0
    detected = result.get("objects", [])
    print(f"  Detected: {len(detected)} objects in {elapsed*1000:.0f}ms")

    gt_objects = ground_truth["fixtures"]["sample_floor_plan.dxf"]["objects"]
    stats = match_objects(detected, gt_objects)
    print_metrics(stats, f"DXF Parser — {dxf_path.name}")

    return stats


def run_pdf_eval(ground_truth: dict) -> dict:
    """Run PDF parser on sample fixture and evaluate."""
    from app.services.pdf_parser import parse_pdf

    pdf_path = FIXTURES / "sample_floor_plan.pdf"
    if not pdf_path.exists():
        print("  ⚠  PDF fixture not found — skipping")
        return {}

    print(f"\n  Parsing: {pdf_path.name}")
    t0 = time.time()
    result = parse_pdf(str(pdf_path))
    elapsed = time.time() - t0
    obj_list = result.objects if hasattr(result, 'objects') else result.get("objects", [])
    # Convert to dicts for matching
    detected = []
    for o in obj_list:
        if hasattr(o, 'model_dump'):
            detected.append(o.model_dump())
        elif isinstance(o, dict):
            detected.append(o)
        else:
            detected.append(vars(o))
    print(f"  Detected: {len(detected)} objects in {elapsed*1000:.0f}ms")

    gt_objects = ground_truth["fixtures"]["sample_floor_plan.pdf"]["objects"]
    stats = match_objects(detected, gt_objects)
    print_metrics(stats, f"PDF Parser — {pdf_path.name}")

    return stats


def run_ai_mock_eval(ground_truth: dict) -> dict:
    """Run AI mock detection and evaluate (mock mode for CI)."""
    from app.ai.mimo_client import MimoVisionClient, MimoConfig

    print("\n  Running AI mock detection...")
    client = MimoVisionClient(MimoConfig(mock_mode=True))
    t0 = time.time()
    result = client.detect_objects("(mock)", prompt="eval test")
    elapsed = time.time() - t0
    detected = [o.model_dump() for o in result.objects]
    print(f"  AI Mock detected: {len(detected)} objects in {elapsed*1000:.0f}ms")

    # Use DXF ground truth for AI eval
    gt_objects = ground_truth["fixtures"]["sample_floor_plan.dxf"]["objects"]
    stats = match_objects(detected, gt_objects)
    print_metrics(stats, "AI Mock Detection")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Detection Eval Script")
    parser.add_argument("--dxf-only", action="store_true")
    parser.add_argument("--pdf-only", action="store_true")
    parser.add_argument("--include-ai", action="store_true")
    args = parser.parse_args()

    print("🏭 Detection Eval — Precision/Recall per Object Type")
    print(f"   Ground truth: {FIXTURES / 'ground_truth.json'}")

    gt = load_ground_truth()
    all_stats = {}

    if not args.pdf_only:
        all_stats["dxf"] = run_dxf_eval(gt)
    if not args.dxf_only:
        all_stats["pdf"] = run_pdf_eval(gt)
    if args.include_ai:
        all_stats["ai"] = run_ai_mock_eval(gt)

    if not all_stats:
        print("No eval runs selected. Use --dxf-only, --pdf-only, or --include-ai")
        sys.exit(1)

    print("✅ Eval complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
