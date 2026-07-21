# Auto Cost Engine — Project Configuration Guide

## How to Add a New Customer Project

The system is designed so that adding a new customer is a **YAML edit, not a code edit**.

### Step 1: Collect Inputs

You need:
1. **Floor plan PDF** (DXF/DWG also supported)
2. **Ground truth BOQ Excel** (optional but recommended for training)
3. **Project name** (e.g., "ABC Office", "XYZ Residence")

### Step 2: Create Project Directory

```bash
mkdir -p seed/projects/<project_name>
```

### Step 3: Copy Reference Files

```bash
# Copy an existing project as a template
cp -r seed/projects/gu_office/* seed/projects/<project_name>/
```

### Step 4: Edit `office_india_v1.yaml`

Update the following:
- `reference:` field with the new project name
- `grand_total:` with the expected total
- `trades:` array — copy the 13 trades or customize for the new project
- Each trade's `items:` — update quantities, rates, and units to match the new project

The YAML structure is:
```yaml
version: 1
building_type: office_fitout  # or: residential, retail, healthcare
reference: "Project Name"
grand_total: 6251940

trades:
  - name: "Civil Work & Plumbing Work"
    expected_total: 1061700
    items:
      - description: "Vitrified tile flooring"
        unit: sft.
        rate: 250
        object_type: flooring
      # ... add all items for this trade
```

### Step 5: Edit `rates_gu_office.yaml`

Update rates to match project requirements:
```yaml
version: 1
project: "Project Name"
reference_totals:
  grand_total: 0  # update to expected

rates:
  vitrified_tile: 250
  gypsum_partition: 200
  # ... all rates
```

### Step 6: Run Training Loop

```bash
python scripts/train_eval.py \
  --project seed/projects/<project_name> \
  --ground-truth /path/to/ground_truth.xlsx \
  --iterations 10
```

The eval loop will:
1. Load project YAML rules
2. Compute BOQ
3. Compare to ground truth
4. Iterate until convergence or max iterations

### Step 7: Verify Output

```bash
# Check the eval report
cat seed/projects/<project_name>/eval_report.md

# Open the BOQ in Excel/LibreOffice
open seed/projects/<project_name>/output_boq.xlsx
```

## Key Principles

1. **Rules are data, not code** — All quantity rules live in YAML files, not in Python source
2. **Rates are per-project** — Each project has its own rates file
3. **Validation is automated** — `make verify-seed` checks all seed data integrity
4. **No TODOs** — Every YAML file must have real data before the system boots

## Troubleshooting

| Issue | Fix |
|-------|-----|
| MiMo API unreachable | Check `MIMO_API_KEY` and `MIMO_API_BASE` env vars |
| Trade total mismatch | Check the trade's items in the YAML file |
| Zero items detected | Check MiMo detection; fall back to ground truth path |
| Missing rates | Add missing rates to `rates_<project>.yaml` |
