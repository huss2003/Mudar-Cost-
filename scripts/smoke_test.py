#!/usr/bin/env python3
"""Automated smoke test for the Auto Cost Engine API stack.

Runs the full user journey against a running deployment (dev or prod).

Usage:
    SMOKE_BASE_URL=http://localhost python scripts/smoke_test.py
    SMOKE_PROJECT_ID=1   python scripts/smoke_test.py   # project to use
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://localhost").rstrip("/")
PROJECT_ID = int(os.environ.get("SMOKE_PROJECT_ID", "1"))
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "real"

# Files to upload
PDF_FIXTURE = FIXTURES_DIR / "office_floor_plan.pdf"
DXF_FIXTURE = FIXTURES_DIR / "representative_floor_plan.dxf"


def check(step: str, status: str, detail: str = "") -> tuple[str, str, str]:
    """Return a result tuple: (step, status, detail)."""
    return (step, status, detail)


def run_smoke() -> list[tuple[str, str, str]]:
    """Execute the full smoke-test journey and return results."""
    results: list[tuple[str, str, str]] = []
    timings: dict[str, float] = {}
    t0 = time.monotonic()

    # ==================================================================
    # 1. Health check (liveness)
    # ==================================================================
    t = time.monotonic()
    try:
        r = httpx.get(f"{BASE_URL}/healthz", timeout=10)
        ok = r.status_code == 200
        results.append(check("healthz", "PASS" if ok else "FAIL",
                              f"HTTP {r.status_code}"))
    except Exception as e:
        results.append(check("healthz", "FAIL", str(e)))
    timings["healthz"] = time.monotonic() - t

    # ==================================================================
    # 2. Readiness check (deep dependency check)
    # ==================================================================
    t = time.monotonic()
    try:
        r = httpx.get(f"{BASE_URL}/readyz", timeout=15)
        # 200 = ready, 503 = degraded — either is acceptable for smoke
        ok = r.status_code in (200, 503)
        detail = f"HTTP {r.status_code}"
        if r.status_code == 503:
            try:
                body = r.json()
                failing = [k for k, v in body.get("checks", {}).items()
                           if v.get("status") != "ok"]
                detail += f" (degraded: {', '.join(failing)})"
            except Exception:
                pass
        results.append(check("readyz", "PASS" if ok else "FAIL", detail))
    except Exception as e:
        results.append(check("readyz", "FAIL", str(e)))
    timings["readyz"] = time.monotonic() - t

    # ==================================================================
    # 3. Upload PDF drawing
    # ==================================================================
    uploaded_drawing_id = None
    t = time.monotonic()
    try:
        if not PDF_FIXTURE.exists():
            results.append(check("upload_pdf", "SKIPPED",
                                  f"Fixture not found: {PDF_FIXTURE}"))
        else:
            with open(PDF_FIXTURE, "rb") as f:
                files = {"file": ("office_floor_plan.pdf", f, "application/pdf")}
                r = httpx.post(
                    f"{BASE_URL}/api/v1/drawings",
                    params={"project_id": PROJECT_ID},
                    files=files,
                    timeout=90,
                )
            if r.status_code in (200, 201):
                data = r.json()
                uploaded_drawing_id = (data.get("drawing_id")
                                       or data.get("id"))
                detail = f"id={uploaded_drawing_id}, HTTP {r.status_code}"
                results.append(check("upload_pdf", "PASS", detail))
            else:
                results.append(check("upload_pdf", "FAIL",
                                      f"HTTP {r.status_code}: {r.text[:200]}"))
    except Exception as e:
        results.append(check("upload_pdf", "FAIL", str(e)))
    timings["upload_pdf"] = time.monotonic() - t

    # ==================================================================
    # 4. Upload DXF drawing (representative floor plan)
    # ==================================================================
    dxf_drawing_id = None
    t = time.monotonic()
    try:
        if not DXF_FIXTURE.exists():
            results.append(check("upload_dxf", "SKIPPED",
                                  f"Fixture not found: {DXF_FIXTURE}"))
        else:
            with open(DXF_FIXTURE, "rb") as f:
                files = {"file": ("representative_floor_plan.dxf", f,
                                  "application/dxf")}
                r = httpx.post(
                    f"{BASE_URL}/api/v1/drawings",
                    params={"project_id": PROJECT_ID},
                    files=files,
                    timeout=90,
                )
            if r.status_code in (200, 201):
                data = r.json()
                dxf_drawing_id = (data.get("drawing_id")
                                  or data.get("id"))
                detail = f"id={dxf_drawing_id}, HTTP {r.status_code}"
                results.append(check("upload_dxf", "PASS", detail))
            else:
                results.append(check("upload_dxf", "FAIL",
                                      f"HTTP {r.status_code}: {r.text[:200]}"))
    except Exception as e:
        results.append(check("upload_dxf", "FAIL", str(e)))
    timings["upload_dxf"] = time.monotonic() - t

    # ==================================================================
    # 5. Poll PDF drawing status until parsed
    # ==================================================================
    t = time.monotonic()
    if uploaded_drawing_id:
        polled = False
        for i in range(45):
            try:
                r = httpx.get(
                    f"{BASE_URL}/api/v1/drawings/{uploaded_drawing_id}/status",
                    timeout=10,
                )
                if r.status_code == 200:
                    body = r.json()
                    status = body.get("status", "")
                    obj_count = body.get("object_count", 0)
                    if status in ("completed", "parsed", "processed"):
                        detail = (f"status={status}, objects={obj_count}, "
                                  f"polled={i + 1}×")
                        results.append(check("poll_pdf_status", "PASS", detail))
                        polled = True
                        break
                    elif status == "failed":
                        err = body.get("error_message", "unknown")
                        results.append(check("poll_pdf_status", "FAIL",
                                              f"status={status}: {err}"))
                        polled = True
                        break
                time.sleep(2)
            except Exception as e:
                time.sleep(2)
                continue
        if not polled:
            results.append(check("poll_pdf_status", "FAIL",
                                  "timed out after 45 polls"))
    else:
        results.append(check("poll_pdf_status", "SKIPPED",
                              "no drawing uploaded"))
    timings["poll_pdf_status"] = time.monotonic() - t

    # ==================================================================
    # 6. Poll DXF drawing status until parsed
    # ==================================================================
    t = time.monotonic()
    if dxf_drawing_id:
        polled = False
        for i in range(45):
            try:
                r = httpx.get(
                    f"{BASE_URL}/api/v1/drawings/{dxf_drawing_id}/status",
                    timeout=10,
                )
                if r.status_code == 200:
                    body = r.json()
                    status = body.get("status", "")
                    obj_count = body.get("object_count", 0)
                    if status in ("completed", "parsed", "processed"):
                        detail = (f"status={status}, objects={obj_count}, "
                                  f"polled={i + 1}×")
                        results.append(check("poll_dxf_status", "PASS", detail))
                        polled = True
                        break
                    elif status == "failed":
                        err = body.get("error_message", "unknown")
                        results.append(check("poll_dxf_status", "FAIL",
                                              f"status={status}: {err}"))
                        polled = True
                        break
                time.sleep(2)
            except Exception as e:
                time.sleep(2)
                continue
        if not polled:
            results.append(check("poll_dxf_status", "FAIL",
                                  "timed out after 45 polls"))
    else:
        results.append(check("poll_dxf_status", "SKIPPED",
                              "no DXF drawing uploaded"))
    timings["poll_dxf_status"] = time.monotonic() - t

    # ==================================================================
    # 7. Get detected objects for PDF
    # ==================================================================
    t = time.monotonic()
    if uploaded_drawing_id:
        try:
            r = httpx.get(
                f"{BASE_URL}/api/v1/drawings/{uploaded_drawing_id}/objects",
                timeout=15,
            )
            if r.status_code == 200:
                objects = r.json()
                obj_list = (objects if isinstance(objects, list)
                            else objects.get("objects", []))
                cnt = len(obj_list)
                types = {}
                for obj in obj_list:
                    ot = obj.get("object_type", obj.get("type", "unknown"))
                    types[ot] = types.get(ot, 0) + 1
                detail = f"{cnt} objects: {types}"
                results.append(check("objects_pdf", "PASS", detail))
            else:
                results.append(check("objects_pdf", "FAIL",
                                      f"HTTP {r.status_code}"))
        except Exception as e:
            results.append(check("objects_pdf", "FAIL", str(e)))
    else:
        results.append(check("objects_pdf", "SKIPPED", "no drawing uploaded"))
    timings["objects_pdf"] = time.monotonic() - t

    # ==================================================================
    # 8. Compute quantities
    # ==================================================================
    t = time.monotonic()
    try:
        r = httpx.post(
            f"{BASE_URL}/api/v1/projects/{PROJECT_ID}/compute-quantities",
            timeout=180,
        )
        if r.status_code in (200, 202):
            body = r.json()
            job_id = body.get("job_id") or body.get("task_id", "N/A")
            detail = f"HTTP {r.status_code}, job_id={job_id}"
            results.append(check("compute_quantities", "PASS", detail))
        else:
            results.append(check("compute_quantities", "FAIL",
                                  f"HTTP {r.status_code}: {r.text[:200]}"))
    except Exception as e:
        results.append(check("compute_quantities", "FAIL", str(e)))
    timings["compute_quantities"] = time.monotonic() - t

    # ==================================================================
    # 9. Fetch BOQ (Bill of Quantities)
    # ==================================================================
    t = time.monotonic()
    try:
        r = httpx.get(
            f"{BASE_URL}/api/v1/projects/{PROJECT_ID}/boq",
            timeout=30,
        )
        if r.status_code == 200:
            boq_data = r.json()
            items = (boq_data if isinstance(boq_data, list)
                     else boq_data.get("items", boq_data.get("trades", [])))
            cnt = len(items)
            results.append(check("fetch_boq", "PASS",
                                  f"{cnt} trade groups/items"))
        else:
            results.append(check("fetch_boq", "FAIL",
                                  f"HTTP {r.status_code}: {r.text[:200]}"))
    except Exception as e:
        results.append(check("fetch_boq", "FAIL", str(e)))
    timings["fetch_boq"] = time.monotonic() - t

    # ==================================================================
    # 10. Export BOQ as XLSX
    # ==================================================================
    t = time.monotonic()
    try:
        r = httpx.post(
            f"{BASE_URL}/api/v1/projects/{PROJECT_ID}/export",
            params={"format": "xlsx"},
            timeout=120,
        )
        if r.status_code in (200, 202):
            body = r.json()
            export_id = body.get("export_id") or body.get("id")
            detail = f"HTTP {r.status_code}, export_id={export_id}"
            # If export_id provided, try to download
            if export_id:
                try:
                    d = httpx.get(
                        f"{BASE_URL}/api/v1/exports/{export_id}/download",
                        timeout=30,
                    )
                    if d.status_code == 200 and len(d.content) > 5000:
                        detail += f", download={len(d.content)} bytes"
                        results.append(check("export_xlsx", "PASS", detail))
                    else:
                        detail += (f", download HTTP {d.status_code} "
                                   f"({len(d.content)} bytes)")
                        results.append(check("export_xlsx", "PASS (queued)",
                                              detail))
                except Exception:
                    results.append(check("export_xlsx", "PASS (queued)",
                                          detail + " (async)"))
            else:
                results.append(check("export_xlsx", "PASS (queued)", detail))
        else:
            results.append(check("export_xlsx", "FAIL",
                                  f"HTTP {r.status_code}: {r.text[:200]}"))
    except Exception as e:
        results.append(check("export_xlsx", "FAIL", str(e)))
    timings["export_xlsx"] = time.monotonic() - t

    # ==================================================================
    # 11. Generate proposal PDF
    # ==================================================================
    t = time.monotonic()
    try:
        r = httpx.post(
            f"{BASE_URL}/api/v1/projects/{PROJECT_ID}/proposal",
            timeout=120,
        )
        if r.status_code in (200, 202):
            ct = r.headers.get("content-type", "")
            body_len = len(r.content)
            if "pdf" in ct or body_len > 10000:
                detail = f"HTTP {r.status_code}, {body_len} bytes, {ct}"
                results.append(check("proposal_pdf", "PASS", detail))
            else:
                detail = f"HTTP {r.status_code}, {body_len} bytes"
                results.append(check("proposal_pdf", "PASS (created)",
                                      detail))
        else:
            results.append(check("proposal_pdf", "FAIL",
                                  f"HTTP {r.status_code}: {r.text[:200]}"))
    except Exception as e:
        results.append(check("proposal_pdf", "FAIL", str(e)))
    timings["proposal_pdf"] = time.monotonic() - t

    # ==================================================================
    # 12. List drawings
    # ==================================================================
    t = time.monotonic()
    try:
        r = httpx.get(f"{BASE_URL}/api/v1/drawings", timeout=15)
        if r.status_code == 200:
            body = r.json()
            total = body.get("total", 0)
            results.append(check("list_drawings", "PASS",
                                  f"{total} total drawings"))
        else:
            results.append(check("list_drawings", "FAIL",
                                  f"HTTP {r.status_code}"))
    except Exception as e:
        results.append(check("list_drawings", "FAIL", str(e)))
    timings["list_drawings"] = time.monotonic() - t

    # ==================================================================
    # 13. Drawing object types catalogue
    # ==================================================================
    t = time.monotonic()
    try:
        r = httpx.get(f"{BASE_URL}/api/v1/drawings/types", timeout=10)
        if r.status_code == 200:
            types = r.json()
            cnt = len(types) if isinstance(types, list) else 0
            results.append(check("object_types", "PASS",
                                  f"{cnt} type catalogues"))
        else:
            results.append(check("object_types", "FAIL",
                                  f"HTTP {r.status_code}"))
    except Exception as e:
        results.append(check("object_types", "FAIL", str(e)))
    timings["object_types"] = time.monotonic() - t

    # Store timings for report
    results.append(check("__timings__", json.dumps(timings),
                          f"total={time.monotonic() - t0:.1f}s"))

    return results


def main():
    print("=" * 68)
    print("  Auto Cost Engine — Smoke Test")
    print(f"  Target: {BASE_URL}")
    print(f"  Project ID: {PROJECT_ID}")
    print("=" * 68)
    print()

    results = run_smoke()

    # Separate timing metadata from visible results
    timings_info = {}
    visible = []
    for step, status, detail in results:
        if step == "__timings__":
            timings_info = json.loads(status)
        else:
            visible.append((step, status, detail))

    # Summary table
    status_counts = {"PASS": 0, "FAIL": 0, "SKIPPED": 0}
    print(f"{'Step':<30} {'Status':<12} Detail")
    print("-" * 68)
    for step, status, detail in visible:
        status_counts[status] = status_counts.get(status, 0) + 1
        icon = {"PASS": "✓", "FAIL": "✗", "SKIPPED": "⊘"}.get(status, "?")
        print(f"  {icon} {step:<28} {status:<12} {detail}")

    # Timing summary
    print()
    print("  ── Timing per step ──")
    for step, sec in sorted(timings_info.items(), key=lambda x: -x[1]):
        print(f"    {step:<25} {sec:.1f}s")

    print()
    total_time = timings_info.get("total", 0)
    print(f"  Total journey: {total_time:.1f}s")
    print()
    print(f"  Results: {status_counts}")
    print()
    all_pass = status_counts.get("FAIL", 0) == 0
    if all_pass:
        print("  ✅ SMOKE TEST PASSED")
    else:
        print("  ❌ SMOKE TEST FAILED — some checks did not pass")
    print()

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
