# Auto Cost Engine — AI-Powered Construction Estimation Platform

> ₹5,000+ worth AI-powered construction cost estimation engine that detects objects from floor plans, computes BOQ, and generates proposals automatically.

**Live App:** [https://auto-cost-engine.vercel.app](https://auto-cost-engine.vercel.app)

---

## What This Is

An AI-powered interior fit-out cost estimation engine that takes a floor plan (PDF/DWG/DXF), detects every room, cabin, partition, door, window, workstation, and furniture piece using MiMo v2.5 vision AI, then computes a complete Bill of Quantities (BOQ) with material rates, labour costs, and a final proposal — all automatically.

**The Problem:** Interior fit-out estimators manually measure every room, partition, door, window, and furniture piece from floor plans. A 1344 sqft office has 13 trades, ~250 line items, and takes 2-3 days to estimate manually.

**The Solution:** Upload a floor plan → AI detects objects → rules compute quantities → materials are priced → proposal is generated. Time: 2 minutes.

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 18 + TypeScript + Vite | SPA with premium UI |
| **UI Library** | Mantine UI | Component library |
| **3D Visualization** | Three.js | Floor plan 3D view |
| **Charts** | Recharts | Cost breakdown visualizations |
| **State Management** | Zustand | Client-side state |
| **Backend Database** | Supabase PostgreSQL | All data storage |
| **Edge Functions** | Supabase Edge Functions (Deno/TypeScript) | API + AI detection |
| **File Storage** | Supabase Storage | Drawing uploads, exports |
| **AI Vision** | MiMo v2.5 (Xiaomi) | Floor plan object detection |
| **AI Text** | MiMo v2.5 | Cost reasoning, optimization |
| **Deployment** | Vercel | Frontend hosting |
| **Database Hosting** | Supabase | PostgreSQL + storage + edge functions |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    USER BROWSER                          │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  React SPA (Vercel)                                │  │
│  │  - Drawings page (upload + view)                   │  │
│  │  - Quantities page (3D view + BOQ table)           │  │
│  │  - Materials page (catalog browser)                │  │
│  │  - Costs page (cost breakdown charts)              │  │
│  │  - AI page (assistant + suggestions)               │  │
│  │  - Exports page (download BOQ/proposal)            │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         │ HTTPS                         │
│  ┌──────────────────────▼────────────────────────────┐  │
│  │  Supabase Edge Functions (Deno)                    │  │
│  │  - /api/detect        → MiMo v2.5 vision call      │  │
│  │  - /api/compute-qty   → BOQ rule engine             │  │
│  │  - /api/compute-cost  → Material rate lookup         │  │
│  │  - /api/export        → Excel/PDF generation         │  │
│  │  - /api/*             → CRUD for projects/drawings   │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         │ HTTPS                         │
│  ┌──────────────────────▼────────────────────────────┐  │
│  │  Supabase PostgreSQL                                │  │
│  │  - projects, drawings, detected_objects             │  │
│  │  - boq_items, cost_versions                         │  │
│  │  - materials, vendors, labour_rates                 │  │
│  │  - pgvector embeddings (for AI search)              │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Supabase Storage                                  │  │
│  │  - drawings/ (uploaded floor plans)                 │  │
│  │  - exports/ (generated BOQ/proposal files)          │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Features

### 1. Drawing Upload & AI Detection
- **Upload:** PDF, DWG, DXF floor plans
- **Detection:** MiMo v2.5 vision AI identifies:
  - Rooms (cabin, meeting room, board room, reception, cafeteria, washroom, server)
  - Doors (glass door, flush door, entrance door)
  - Windows (aluminium sliding, glass facade)
  - Partitions (gypsum, glass with aluminium frame)
  - Furniture (desks, conference tables, reception desk)
  - Workstations (modular, 1200×750mm)
- **3D Visualization:** Three.js renders detected objects in 3D with finish presets
- **2D Viewer:** SVG overlay of detected objects on the floor plan

### 2. Bill of Quantities (BOQ)
- **13 Trades:** Civil, Plumbing, POP/Gypsum, Carpentry, Painting, Modular Furniture, Chairs, Finishing, Electrical, PA System, Fire Alarm, Sprinkler, HVAC
- **250+ Line Items:** Each with quantity, unit, rate, amount
- **Derived Formulas:** Quantities computed from detected geometry (not hand-keyed)
  - `vitrified_flooring = office_footprint - washroom_area - server_area`
  - `gypsum_partition = cabin_perimeter × 8ft_height`
  - `electrical_points = per_room_density × room_count`
- **Real Material Rates:** 51 materials from Indian market (Saint Gobain, Kajaria, Asian Paints, Godrej, Legrand)

### 3. Material Intelligence
- **51 Materials:** Glass, gypsum, flooring, paint, furniture, electrical, HVAC, fire safety
- **16 Vendors:** Real Indian suppliers with GSTINs
- **Material Substitution:** Click any material to see alternatives
- **Rate Lookups:** Material Master → rate → line amount
- **Brand Selection:** Approved brand lists per trade

### 4. Cost Engine
- **Live Cost Calculation:** Material rate + labour rate + equipment cost
- **Trade Breakdown:** Cost per trade with percentages
- **Version History:** Track cost changes over time
- **Export:** Generate Excel BOQ and Proposal PDF

### 5. AI Features
- **Vision Detection:** MiMo v2.5 analyzes floor plans
- **Cost Optimization:** AI suggests cheaper alternatives
- **Anomaly Detection:** Flags unusually high/low quantities
- **Proposal Generation:** AI writes project descriptions

### 6. Export
- **Excel BOQ:** Full Bill of Quantities with trade groupings
- **Proposal PDF:** Branded proposal with scope, BOQ, terms
- **Purchase List:** Material quantities for procurement
- **Client Presentation:** Summary for client approval

---

## API Endpoints

### Supabase Edge Functions

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/functions/v1/detect` | POST | AI detection on floor plan image |
| `/functions/v1/compute-quantities` | POST | Compute BOQ from detected objects |
| `/functions/v1/compute-costs` | POST | Calculate costs from BOQ items |
| `/functions/v1/export` | POST | Generate Excel/PDF exports |
| `/functions/v1/api/*` | ALL | CRUD operations + routing |

### Direct Supabase Queries

| Table | Operations |
|-------|-----------|
| `projects` | CRUD project metadata |
| `drawings` | Upload/manage floor plans |
| `detected_objects` | Store AI detection results |
| `boq_items` | Bill of Quantities line items |
| `cost_versions` | Cost calculation versions |
| `materials` | Material catalog |
| `vendors` | Vendor/supplier database |
| `labour_rates` | Labour cost rates |
| `boq_rules` | Quantity computation rules |
| `rate_mappings` | Object type → material rate links |

---

## Database Schema (Supabase)

### Core Tables
```sql
projects          → project metadata, status, client info
drawings          → uploaded files, detection status, SHA-256 hash
detected_objects  → AI-detected rooms, doors, furniture (bbox, type, confidence)
boq_items         → Bill of Quantities (trade, description, qty, unit, rate, amount)
cost_versions     → cost calculations (materials, labour, equipment, total)
```

### Reference Data
```sql
materials         → 51 materials (glass, gypsum, flooring, paint, furniture...)
vendors           → 16 Indian suppliers with GSTINs
labour_rates      → 10 labour categories (carpenter, electrician, painter...)
boq_rules         → quantity computation formulas
rate_mappings     → object_type → material_code → rate links
```

### AI Support
```sql
ai_opportunities  → AI-suggested optimizations
embeddings        → pgvector embeddings for semantic search
```

---

## Environment Variables

### Frontend (Vercel)
```bash
VITE_SUPABASE_URL=https://pecnshwflkwpnwiskgmg.supabase.co
VITE_SUPABASE_ANON_KEY=sb_publishable_GMkHBBICoUbKeg5W1UGtFg_Y-_xU0yb
VITE_ENVIRONMENT=production
```

### Supabase Edge Functions
```bash
SUPABASE_URL=https://pecnshwflkwpnwiskgmg.supabase.co
SUPABASE_ANON_KEY=sb_publishable_GMkHBBICoUbKeg5W1UGtFg_Y-_xU0yb
MIMO_API_KEY=sk-sj2opp4kpvdf8lg25py9mzjo1frd1w7uw65u1hquck807kx2
```

---

## Project Structure

```
auto-cost-engine/
├── frontend/                    # React SPA
│   ├── src/
│   │   ├── api/
│   │   │   └── supabase.ts     # Supabase client
│   │   ├── components/
│   │   │   ├── Layout.tsx       # Main layout with sidebar
│   │   │   ├── ThreeViewer.tsx  # 3D visualization
│   │   │   └── DrawingViewer2D.tsx  # 2D overlay
│   │   ├── pages/
│   │   │   ├── Drawings.tsx     # Upload + manage drawings
│   │   │   ├── Quantities.tsx   # BOQ + 3D view
│   │   │   ├── Materials.tsx    # Material catalog
│   │   │   ├── Costs.tsx        # Cost breakdown
│   │   │   ├── AI.tsx           # AI assistant
│   │   │   └── Exports.tsx      # Download exports
│   │   ├── store/               # Zustand stores
│   │   ├── index.css            # Premium CSS foundation
│   │   └── App.tsx              # Router + providers
│   ├── package.json
│   └── vite.config.ts
│
├── supabase/                    # Supabase Edge Functions
│   └── functions/
│       ├── detect/
│       │   └── index.ts         # MiMo v2.5 vision detection
│       ├── compute-quantities/
│       │   └── index.ts         # BOQ rule engine
│       ├── compute-costs/
│       │   └── index.ts         # Cost calculation
│       ├── export/
│       │   └── index.ts         # Excel/PDF generation
│       └── api/
│           └── index.ts         # Main router + CRUD
│
├── backend/                     # Python backend (local dev)
│   ├── app/
│   │   ├── ai/
│   │   │   ├── mimo_client.py   # MiMo v2.5 client
│   │   │   ├── deepseek_client.py  # DeepSeek client (fallback)
│   │   │   ├── pipeline.py      # AI detection pipeline
│   │   │   └── training.py      # Training loop
│   │   ├── services/
│   │   │   ├── rule_engine.py   # Quantity rule evaluator
│   │   │   ├── cost_engine.py   # Cost calculation
│   │   │   ├── material_selector.py  # Material lookup
│   │   │   └── export_service.py  # Excel/PDF generation
│   │   ├── routers/
│   │   │   ├── drawings.py      # Drawing endpoints
│   │   │   ├── quantities.py    # BOQ endpoints
│   │   │   ├── materials.py     # Material endpoints
│   │   │   └── costs.py         # Cost endpoints
│   │   └── models/              # SQLAlchemy models
│   ├── seed/
│   │   ├── reference/
│   │   │   ├── materials.yaml   # 51 materials
│   │   │   └── vendors.yaml     # 16 vendors
│   │   ├── rules/
│   │   │   ├── office_india_v1.yaml  # Quantity rules
│   │   │   └── rate_mapping.yaml     # Rate lookups
│   │   └── projects/
│   │       └── gu_office/       # G.U. Office training data
│   ├── tests/
│   │   ├── test_rule_engine.py  # Rule engine tests
│   │   ├── test_cost_engine.py  # Cost engine tests
│   │   └── eval/                # Training evaluation
│   ├── Dockerfile
│   └── requirements.txt
│
├── vercel.json                  # Vercel deployment config
├── Dockerfile                   # Backend Docker build
├── Makefile                     # Dev commands
└── README.md                    # This file
```

---

## Development

### Prerequisites
- Node.js 20+
- Python 3.12+
- Supabase account (for database + edge functions)
- MiMo v2.5 API key (for AI detection)

### Local Development
```bash
# Clone the repo
git clone https://github.com/huss2003/Mudar-Cost-.git
cd Mudar-Cost-

# Install frontend dependencies
cd frontend && npm install

# Start frontend dev server
npm run dev
# → http://localhost:5173

# Backend (for local testing)
cd ../backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# → http://localhost:8000
```

### Supabase Setup
1. Create a Supabase project
2. Run the migration SQL to create tables
3. Enable pgvector extension
4. Create storage buckets: `drawings`, `exports`
5. Deploy edge functions:
```bash
supabase functions deploy detect
supabase functions deploy compute-quantities
supabase functions deploy compute-costs
supabase functions deploy export
supabase functions deploy api
```

### Environment Variables
Set these in Supabase Dashboard → Edge Functions → Secrets:
```bash
MIMO_API_KEY=sk-sj2opp4kpvdf8lg25py9mzjo1frd1w7uw65u1hquck807kx2
```

### Deploy to Vercel
```bash
# Link to Vercel
vercel link

# Set environment variables
vercel env add VITE_SUPABASE_URL production
vercel env add VITE_SUPABASE_ANON_KEY production

# Deploy
vercel --prod
```

---

## Testing

### Backend Tests
```bash
cd backend && python -m pytest tests/ -q
# 278 passed, 13 skipped
```

### Frontend Build
```bash
cd frontend && npx tsc --noEmit && npm run build
```

### Training Loop
```bash
cd backend && python -m app.ai.training
```

### Generalization Test
```bash
cd backend && python scripts/generalize_test.py
```

---

## AI Configuration

### MiMo v2.5 (Vision + Text)
- **Endpoint:** `https://api.xiaomimimo.com/v1/chat/completions`
- **Model:** `mimo-v2.5`
- **Auth:** `api-key` header (not Bearer)
- **Max Tokens:** 8192
- **Cost:** ~$0.002-0.007 per call

### Detection Pipeline
1. Upload floor plan → Supabase Storage
2. Rasterize to PNG (300 DPI)
3. Send to MiMo v2.5 with structured prompt
4. Parse JSON response → detected objects
5. Store in `detected_objects` table
6. Compute BOQ using derived formulas
7. Price materials from Material Master

---

## Trained Data

### G.U. Office Interior Layout (Training Set)
- **Area:** 24' × 56'1" (1344 sqft)
- **Trades:** 13
- **Line Items:** 96
- **Grand Total:** ₹62,51,940
- **Detection F1:** 1.0 (all categories)

### Held-Out Validation
- **Clinic Fit-out:** 346 sqft, 3 rooms → PASS
- **Small Office:** 450 sqft, 2 cabins → PASS (3/4 checks)
- **Trade Structure:** Stable across customers

---

## Production Deployment

### Vercel (Frontend)
- **URL:** https://auto-cost-engine.vercel.app
- **Build:** Vite → static files
- **Routing:** SPA with fallback

### Supabase (Backend + Database)
- **Database:** PostgreSQL with pgvector
- **Edge Functions:** Deno/TypeScript
- **Storage:** File uploads + exports
- **Auth:** Supabase Auth (optional)

### Backup
- Daily automated backups via Supabase
- Manual backup: Supabase Dashboard → Database → Backups

---

## License

Private — Jasfo Design, India

---

## Contact

**Jasfo Design** — Interior Fit-Out Cost Estimation
- Website: [jasfo.in](https://jasfo.in)
- Email: info@jasfo.in

---

## Acknowledgments

- **MiMo v2.5** by Xiaomi — Vision AI for floor plan detection
- **Supabase** — Database, storage, and edge functions
- **Vercel** — Frontend deployment
- **Three.js** — 3D visualization
- **Mantine UI** — Component library
