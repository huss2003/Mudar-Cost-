# Auto Cost Engine — Smoke Test Report

**Date:** 2026-07-22  
**Target:** `http://localhost:8000`  
**Project ID:** 1  
**Smoke Test Script:** `scripts/smoke_test.py`  
**Test Fixtures:** `tests/fixtures/real/`

---

## Test Fixtures

| Fixture | Path | Size | Description |
|---------|------|------|-------------|
| GU Office Floor Plan (PDF) | `tests/fixtures/real/office_floor_plan.pdf` | 460,770 B | Real-world AutoCAD export — single page, 24' × 56'1" GU Office layout |
| Representative Floor Plan (DXF) | `tests/fixtures/real/representative_floor_plan.dxf` | 26,273 B | Generated floor plan: 3 rooms, 2 doors, 4 windows, CAD layers |

### DXF Fixture Details (`representative_floor_plan.dxf`)

**Overall envelope:** 28' × 30' (8,534 mm × 9,144 mm)

| Room | Dimensions | Location |
|------|-----------|----------|
| Room 1 — Office | 10' × 12' (3,048 × 3,658 mm) | Bottom-left |
| Room 2 — Conference | 8' × 10' (2,438 × 3,048 mm) | Bottom-right |
| Room 3 — Storage | 6' × 8' (1,829 × 2,438 mm) | Top-left |

**Objects per CAD layer:**

| Layer | Objects | Count |
|-------|---------|-------|
| `A-WALL` | Outer walls (4) + internal partitions (2) | 6 lines |
| `A-DOOR` | Door blocks + swing arcs | 2 doors |
| `A-GLAZ` | Window double-lines + hatch markers | 4 windows |
| `A-ANNO-TEXT` | Room labels + dimension notes | 7 texts |

---

## Smoke Test Journey Results

```
====================================================================
  Auto Cost Engine — Smoke Test
  Target: http://localhost:8000
  Project ID: 1
====================================================================

Step                           Status       Detail
--------------------------------------------------------------------
  ✗ healthz                      FAIL         Connection refused
  ✗ readyz                       FAIL         Connection refused
  ✗ upload_pdf                   FAIL         Connection refused
  ✗ upload_dxf                   FAIL         Connection refused
  ⊘ poll_pdf_status              SKIPPED      no drawing uploaded
  ⊘ poll_dxf_status              SKIPPED      no DXF drawing uploaded
  ⊘ objects_pdf                  SKIPPED      no drawing uploaded
  ✗ compute_quantities           FAIL         Connection refused
  ✗ fetch_boq                    FAIL         Connection refused
  ✗ export_xlsx                  FAIL         Connection refused
  ✗ proposal_pdf                 FAIL         Connection refused
  ✗ list_drawings                FAIL         Connection refused
  ✗ object_types                 FAIL         Connection refused

  ── Timing per step ──
    healthz                   4.2s
    upload_dxf                4.1s
    export_xlsx               4.1s
    upload_pdf                4.1s
    compute_quantities        4.1s
    proposal_pdf              4.1s
    readyz                    4.1s
    list_drawings             4.1s
    object_types              4.1s
    fetch_boq                 4.1s
    poll_pdf_status           0.0s
    poll_dxf_status           0.0s
    objects_pdf               0.0s

  Total journey: 0.0s
  Results: {'PASS': 0, 'FAIL': 10, 'SKIPPED': 3}
```

**Status:** ❌ FAILED — the backend stack was not running at test time.

---

## Expected Results (when stack is running)

The smoke test exercises 13 checkpoints across the full API journey. Below is the expected outcome for each when all services are healthy.

| # | Step | Expected | Validation |
|---|------|----------|------------|
| 1 | `healthz` | PASS (HTTP 200) | Liveness probe always returns 200 |
| 2 | `readyz` | PASS (HTTP 200) or PASS (HTTP 503 degraded) | Deep dependency check; 200 if all deps healthy, 503 if some missing (still acceptable) |
| 3 | `upload_pdf` | PASS (HTTP 201) | Upload GU Office PDF → returns `drawing_id` |
| 4 | `upload_dxf` | PASS (HTTP 201) | Upload representative DXF → returns `drawing_id` |
| 5 | `poll_pdf_status` | PASS | Poll `/status` until `status` = `completed`/`parsed`/`processed`; expected object_count > 0 |
| 6 | `poll_dxf_status` | PASS | Same as above for DXF; expected object_count ≥ 10 (walls, doors, windows, text) |
| 7 | `objects_pdf` | PASS | Returns detected objects list; count > 0 |
| 8 | `compute_quantities` | PASS (HTTP 200/202) | Dispatches Celery compute; returns `job_id` |
| 9 | `fetch_boq` | PASS (HTTP 200) | Returns BOQ with trade groups |
| 10 | `export_xlsx` | PASS (HTTP 200/202) | Generates XLSX export; download ≥ 5,000 bytes |
| 11 | `proposal_pdf` | PASS (HTTP 200) | Generates proposal PDF; ≥ 10,000 bytes |
| 12 | `list_drawings` | PASS (HTTP 200) | Lists all drawings; `total` ≥ 2 |
| 13 | `object_types` | PASS (HTTP 200) | Returns object type catalogue |

### Expected Object Counts (detection)

**PDF (GU Office Floor Plan):**
- Walls: 4+ (outer envelope)
- Doors: 1+ (entrance)
- Windows: 1+ 
- Room labels and annotations

**DXF (Representative Floor Plan):**
- Walls: 6 (4 outer walls + 2 internal partitions)
- Doors: 2 (900 mm swing doors)
- Windows: 4 (double-line rep with hatch markers)
- Text annotations: 7 (room labels + dimension notes)

---

## Makefile Target

```makefile
.PHONY: smoke
smoke: ## Run smoke tests against the deployed stack
	SMOKE_BASE_URL=http://localhost python scripts/smoke_test.py
```

Usage:
```bash
# Default (dev stack on localhost:80)
make smoke

# Custom base URL
SMOKE_BASE_URL=http://localhost:8000 make smoke

# Custom project ID
SMOKE_PROJECT_ID=1 make smoke
```

---

## Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `tests/fixtures/real/office_floor_plan.pdf` | Created | Real GU Office PDF fixture (460 KB) |
| `tests/fixtures/real/representative_floor_plan.dxf` | Created | Generated DXF with 3 rooms, 2 doors, 4 windows (26 KB) |
| `tests/fixtures/real/generate_dxf.py` | Created | DXF generator script |
| `scripts/smoke_test.py` | Created | Automated smoke test (13-check journey) |
| `Makefile` | Modified | Added `smoke` and `smoke-prod` targets |

---

## Troubleshooting Notes

1. **Backend not running:** Run `make up` to start the dev stack before `make smoke`.
2. **No project exists:** The smoke test uses `project_id=1` by default. Create a project first or set `SMOKE_PROJECT_ID`.
3. **Celery not processing:** Ensure `celery_worker` is running for parsing/compute/export steps.
4. **Auth required:** The `/drawings` upload endpoint does not require auth, but some routes may. If getting 401, the script needs token exchange.
5. **Connection refused:** Confirm backend is listening on the expected port. Default dev: `:8000`, Caddy reverse proxy: `:80`.
6. **Rate limiting:** The API allows 100 req/min per IP. Smoke test runs ~20 requests — well within limits.
