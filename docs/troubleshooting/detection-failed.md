# Detection Failed — Troubleshooting Guide

This document helps you debug a failed MiMo (vision) detection during either:

- **Production pipeline** — the Celery task `process_drawing_ai` in
  `backend/app/tasks/ai_drawings.py`
- **Training loop** — the training iteration in
  `backend/app/ai/training.py` (uses `ReraiseMimoVisionClient`)

## Quick Reference

| Symptom | Most Likely Cause | First Action |
|---------|-------------------|--------------|
| `MiMo API failed after N retries` | Network / endpoint unreachable | Check endpoint & connectivity |
| `HTTP 401` | API key is invalid or missing | Check `MIMO_API_KEY` env var |
| `HTTP 429` | Rate-limited | Wait, or check usage quota |
| `HTTP 5xx` | Server-side error | Retry; if persistent, contact provider |
| `Image not found` | Rasterizer failed or path wrong | Check rasterizer output |
| `Response parse error` | LLM returned malformed JSON | Inspect raw response |
| `ABORTING training iteration` | Area cross-check failed | Check area validation below |
| Mock mode auto-enabled | Dev env with no API key | Set `MIMO_API_KEY` or switch ENVIRONMENT |

---

## 1. Check the Prometheus Metrics

The system exposes detection-related metrics at `/metrics`:

```
# Count of mock-mode fallbacks (dev + no key)
ace_mock_mode_fallback_total{provider="mimo",model="mimo-v2.5"}

# Total AI calls broken down by outcome
ace_ai_calls_total{provider="mimo",model="mimo-v2.5",outcome="success"}
ace_ai_calls_total{provider="mimo",model="mimo-v2.5",outcome="failed"}
ace_ai_calls_total{provider="mimo",model="mimo-v2.5",outcome="mock"}
```

A non-zero `mock_mode_fallback_total` with `outcome="failed"` calls means
the pipeline is running in degraded mode — it silently skips AI detection
and falls back to rule-based results.

---

## 2. Verify the MiMo Endpoint

The MiMo endpoint is configured in `backend/app/ai/mimo_client.py`
(default: ``https://api.opencode.ai/v1/chat/completions``) and can be
overridden via `MIMO_API_BASE`.

Test reachability from the worker container:

```bash
curl -s -o /dev/null -w "%{http_code}" https://api.opencode.ai/v1/chat/completions
```

Expected: `401` (unauthorized — means the endpoint is reachable but
needs a key).

```bash
# Quick DNS check
nslookup api.opencode.ai
```

If DNS fails:

1. Check `/etc/resolv.conf` inside the container.
2. Verify the Docker network (``docker network inspect auto-cost_default``)
   allows outbound `HTTPS (443)` traffic.
3. Some corporate/cloud networks block outbound traffic — open a firewall
   rule for `api.opencode.ai:443`.

---

## 3. Check the API Key

| Environment Variable | Default | Required In |
|---------------------|---------|-------------|
| `MIMO_API_KEY` | `""` | production |

```bash
# Inside the worker / API container
echo "MIMO_API_KEY=${MIMO_API_KEY:-(not set)}"
```

If the variable is empty in production, the `MimoVisionClient` raises a
`ValueError` at construction time.  In development/staging it auto-enables
mock mode and logs a `mock_mode_fallback` metric.

---

## 4. Examine Logs

### Celery task logs

```bash
# Real-time
docker logs -f auto-cost-worker 2>&1 | grep -E "MiMo|mimo|detection|ai_call"

# Structured (structlog) — find a specific trace
docker logs auto-cost-worker 2>&1 | grep "trace_id=xyz"
```

Key log events to look for:

| Event | Meaning |
|-------|---------|
| `ai_call` with `status="success"` | Detection succeeded |
| `ai_call` with `status="failed"` | Detection failed after retries |
| `ai_call` with `status="mock"` | Mock mode (dev, no API key) |
| `Cache HIT` | sha256 cache re-used |
| `Cache read error` | Cache file corrupted or unreadable |
| `Area cross-check FAILED` | Training iteration aborted (see §7) |

### Training loop logs

Run the training script with `LOG_LEVEL=DEBUG`:

```bash
LOG_LEVEL=DEBUG python -m backend.app.ai.training
```

---

## 5. Inspect the sha256 Cache

Detection results are cached at `/tmp/work/cache/pdf_<sha256[:12]>/mimo_response.json`.

```bash
# List cache entries
ls -la /tmp/work/cache/pdf_*/

# Inspect a specific entry
cat /tmp/work/cache/pdf_<prefix>/mimo_response.json | jq .
```

A cache entry is **valid** when:

- `status` is `"completed"`
- `sha256` matches the current file's digest
- The JSON is parseable

If a cache entry is **stale or corrupted**, delete it and re-run:

```bash
rm -rf /tmp/work/cache/pdf_<prefix>
```

To bypass the cache entirely (for debugging), set:

```python
# In pipeline.py or training.py, skip the get_cached_result() call
```

---

## 6. Debug a Failed API Call

Reproduce the API call manually to isolate network / parsing issues.

```bash
# 1. Rasterize a PDF to PNG
python -c "
from app.ai.rasterizer import rasterize_drawing
paths = rasterize_drawing('/path/to/drawing.pdf', dpi=150)
print(paths)
"

# 2. Call the MiMo API directly
IMAGE_B64=$(base64 -w0 /path/to/rasterized_page.png)
curl -s -X POST https://api.opencode.ai/v1/chat/completions \
  -H "Authorization: Bearer ${MIMO_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"mimo-v2.5\",
    \"messages\": [
      {\"role\": \"system\", \"content\": \"You are a CAD drawing analyzer...\"},
      {\"role\": \"user\", \"content\": [
        {\"type\": \"text\", \"text\": \"List all visible objects...\"},
        {\"type\": \"image_url\", \"image_url\": {\"url\": \"data:image/png;base64,${IMAGE_B64}\"}}
      ]}
    ],
    \"max_tokens\": 4096
  }" | jq .
```

If the raw API call succeeds but the pipeline fails, the issue is in
JSON parsing (`_parse_objects_json` in `mimo_client.py`).

---

## 7. Area Cross-Check Failures

The training loop runs an area cross-check after detection.  The GU Office
floor plan title block states **24' x 56'1" = 1344 sqft**.

### Why it fails

| Cause | What to Check |
|-------|---------------|
| MiMo detected only a few objects | Run detection again, check the rasterised image quality |
| Objects have no `area` field | The MiMo response may not include area; check `_build_detected_object` |
| Raster DPI / scale mismatch | Verify `drawing_scale` in `MimoConfig` (default 1:100) |
| Wrong title-block area | Check the PDF title block for the actual dimensions |

### Bypass (debugging only)

Pass `title_block_area_sqft=None` to `run_training_detection()` to skip
the cross-check:

```python
from app.ai.training import run_training_detection
result = run_training_detection(
    image_paths=["page_1.png"],
    title_block_area_sqft=None,  # skip validation
)
```

---

## 8. Rasterizer Issues

If the rasterizer produces no PNG pages:

1. Check that the file is a valid PDF/DXF.
2. Check that `pymupdf` (for PDF) and `ezdxf` (for DXF) are installed.
3. Run the rasterizer directly:

```bash
python -c "
from app.ai.rasterizer import rasterize_drawing
paths = rasterize_drawing('/path/to/file.pdf', dpi=150)
print(f'Pages: {paths}')
"
```

---

## 9. Training Loop: No Fallback Guarantee

The training loop in `backend/app/ai/training.py` uses
`ReraiseMimoVisionClient`, which guarantees:

1. **No mock mode** — `mock_mode` is forced `False` at construction.
2. **No silent degradation** — every failure becomes a `RuntimeError`.
3. **No ground-truth fallback** — failed iterations abort.

If you see a training iteration completing with zero AI objects or with
data that looks like ground truth, the training code has a bug — open a
ticket immediately.

---

## 10. Emergency Recovery

Reset the cache and re-run detection from scratch:

```bash
# 1. Clear the detection cache
rm -rf /tmp/work/cache/pdf_*/

# 2. Reset the drawing status in the database
#    (requires psql access to Postgres)
psql "$DATABASE_URL" -c "
  UPDATE drawings
  SET status = 'uploaded', error_message = NULL, processed_at = NULL
  WHERE id = <drawing_id>;
"

# 3. Re-trigger the AI enhancement task
#    (via Celery shell or API)
python -c "
from app.tasks.ai_drawings import process_drawing_ai
process_drawing_ai.delay(drawing_id=42, minio_object_key='path/to/file.pdf', file_type='pdf')
"
```
