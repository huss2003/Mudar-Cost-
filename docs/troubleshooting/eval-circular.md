# Circular Eval — How to Recognise and Avoid It

## What is a Circular Eval?

A **circular evaluation** is any evaluation that measures your pipeline against the
same data that was used to construct, tune, or fit the pipeline.  Because the
pipeline was *fitted* to the very data it is being judged against, the evaluation
metrics appear deceptively good and hide real-world failures.

In the **Auto Cost Engine** project the classic circular pattern was:

```
Excel Ground Truth  ──encode──▶  YAML BOQ Rules  ──run eval──▶  Same Ground Truth
                                    │
                              Delta = 0.00%   ✘ Circular!
```

The pipeline extracts quantities from the same Excel sheet it was trained on,
encodes those quantities as YAML rules, runs the rules, and claims 0.00% error.
This tells you **nothing** about whether the pipeline works on a real unseen drawing.

---

## How to Detect a Circular Eval

Ask these questions:

| Question | Red flag (circular) | Green flag (honest) |
|----------|---------------------|---------------------|
| **Training data overlap** | Training and eval use the same ground truth | Eval uses a **held-out** PDF, DXF, or Excel that was never touched during development |
| **Rule origin** | Rules were hand-encoded from the eval ground truth | Rules come from a separate reference library, industry standards, or a different source |
| **Mock mode** | Eval claims PASS with `mock_mode=True` or `source="mock"` | Eval refuses to run without a real PDF and real API calls |
| **API calls** | `api_calls == 0` in the iteration report | At least one real API call was logged |
| **Overfitting symptom** | 99%+ precision/recall on training data but 0 items on held-out data | Metrics degrade gracefully on unseen data |

---

## Symptoms of Circular Eval in Auto Cost Engine

1. **Mock-mode PASS**  
   The eval runs `MimoConfig(mock_mode=True)`, which returns 3 pre-canned objects
   (wall, door, window).  These happen to match the ground truth perfectly
   because they were written to.  The eval reports 100% precision / 100% recall
   — but the real pipeline may produce nothing.

2. **Zero API calls**  
   The eval summary claims PASS with `api_calls: 0`.  No real vision model was
   ever invoked.  The "AI" pipeline is a stub.

3. **Same fixture for training and eval**  
   Ground truth from `sample_floor_plan.pdf` was used to write the PDF parser
   rules *and* to validate them.  The parser is tuned to exactly these 6 objects.

4. **No held-out generalisation**  
   The project has a real, larger floor plan at
   `tests/fixtures/real/office_floor_plan.pdf` but it was never used in any eval.

---

## How the Full Pipeline Eval Prevents Circularity

The script `tests/eval/eval_full_pipeline.py` enforces four guardrails:

### 1. Source Verification (rejects mock mode)

```python
extracted = json.load(open(EXTRACTED_OBJECTS_PATH))
if extracted.get("source") != "pdf":
    raise ValueError(...)
```

The eval creates an `extracted_objects.json` artifact after running the real
PDF parser.  If the source is anything other than `"pdf"` the eval refuses
to claim PASS.

### 2. API Call Verification (rejects zero-call runs)

```python
if cloud_spend[iteration_id]["api_calls"] == 0:
    raise ValueError(...)
```

The eval creates a `cloud_spend.json` artifact.  Any iteration with
`api_calls == 0` is flagged and cannot pass.

### 3. Derivation Traceability (prevents hidden circularity)

Every line item in the eval report carries a `derivation` block:

```json
{
  "derivation": {
    "formula": "A * 4",
    "source_objects": [
      {"object_type": "partition", "id": 42, "area": 18.5}
    ],
    "rule_id": "gypsum_partition/rule_007",
    "rule_description": "Gypsum board 12mm (two layers each side)"
  }
}
```

A reviewer can follow the chain: **line item → formula → detected object → PDF**.
If the derivation points back to the same Excel that was used to write the rule,
the circularity is exposed.

### 4. Generalization Test (flags MODEL-OVERFIT)

After the pipeline passes its own eval, the script runs the *entire* pipeline
on `office_floor_plan.pdf` (a held-out PDF that was never used in development).
If any of these fail, the eval exits with code `2` (MODEL-OVERFIT):

- Line count > 0
- At least 3 distinct trades detected
- Grand total > ₹0
- No Python exceptions

---

## How to Run a Non-Circular Eval

```bash
# Basic eval (refuses mock mode by default — requires --api-calls to pass)
python backend/tests/eval/eval_full_pipeline.py --api-calls 1

# Eval with held-out generalisation test
python backend/tests/eval/eval_full_pipeline.py \
    --pdf backend/tests/fixtures/sample_floor_plan.pdf \
    --held-out tests/fixtures/real/office_floor_plan.pdf \
    --api-calls 1

# Skip held-out test (not recommended for release)
python backend/tests/eval/eval_full_pipeline.py --skip-held-out --api-calls 1
```

> **Important:** `--api-calls N` must reflect the actual number of real API
> invocations.  Passing `--api-calls 1` when the pipeline ran in mock mode
> is itself a form of eval fraud and defeats the guard.

---

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| `0` | PASS — all checks passed | Release pipeline is healthy |
| `1` | FAIL — mock check, API check, or derivation check failed | Fix the pipeline before releasing |
| `2` | MODEL-OVERFIT — passes own eval but fails on held-out data | Investigate: the pipeline is memorising rather than generalising |

---

## Checklist for Every Eval Run

- [ ] The PDF fixture exists and is a **real** drawing file, not a stub
- [ ] `extracted_objects.json` shows `source: "pdf"` for every object
- [ ] `cloud_spend.json` shows `api_calls > 0` for this iteration
- [ ] Every line item has a `derivation` block with `formula`, `source_objects`, `rule_id`
- [ ] The held-out PDF (`office_floor_plan.pdf`) produces > 0 items, >= 3 trades, grand total > 0
- [ ] The training ground truth (`ground_truth.json`) was NOT used as an input
- [ ] No data file under `seed/` was derived from any eval fixture
