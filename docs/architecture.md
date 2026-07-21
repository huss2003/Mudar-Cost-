# System Architecture

## Overview

The Auto Cost Engine is a cloud-native application that automates interior fit-out cost estimation. It processes CAD drawings and PDF specifications through an AI pipeline to extract material quantities, maps them against a cost database, and generates detailed Bill of Quantities (BOQ) reports.

The system follows a **microservices-inspired architecture** with clearly separated concerns, running in Docker containers orchestrated by Docker Compose.

---

## Component Descriptions

### 1. Frontend (Vite + React + TypeScript)

- **Role:** User interface for uploading drawings, reviewing extracted quantities, editing BOQ items, and exporting reports.
- **Tech:** React 18, TypeScript, Vite, Tailwind CSS, Playwright (E2E tests).
- **Port:** `80` (served via Caddy reverse proxy in production; dev server on `5173`).
- **Container:** `frontend/` — multi-stage Docker build with Nginx static serving or Vite dev server.

### 2. Caddy (Reverse Proxy)

- **Role:** TLS termination, request routing, static asset serving, and rate limiting.
- **Tech:** Caddy v2 with automatic HTTPS via Let's Encrypt.
- **Config:** `infra/Caddyfile`
- **Key responsibilities:**
  - Route `/api/*` to the backend service.
  - Route `/auth/*` to Keycloak.
  - Serve the frontend static build.
  - Handle CORS headers and WebSocket upgrades (if needed).

### 3. Backend (FastAPI + Python 3.12)

- **Role:** Core API server handling authentication, file uploads, AI inference orchestration, quantity extraction, cost calculation, and BOQ generation.
- **Tech:** FastAPI, SQLAlchemy (async), Alembic (migrations), Celery (async tasks), Pydantic (validation).
- **Port:** `8000`
- **Key endpoints:**
  - `POST /api/upload` — Upload CAD/PDF files.
  - `POST /api/extract` — Trigger AI-powered quantity extraction.
  - `GET /api/projects/{id}/boq` — Retrieve generated BOQ.
  - `GET /api/materials` — List available materials with unit costs.
  - `POST /api/export` — Export BOQ as PDF/Excel.
- **Container:** `backend/Dockerfile`

### 4. PostgreSQL + pgvector

- **Role:** Primary database for projects, materials, cost data, user accounts, and vector embeddings for similarity search.
- **Tech:** PostgreSQL 16 with `pgvector` extension.
- **Port:** `5432`
- **Data:** Persisted via Docker volume `postgres_data`.
- **Migrations:** Managed via Alembic in `backend/alembic/`.

### 5. MinIO (S3-Compatible Object Store)

- **Role:** Stores uploaded CAD drawings, PDFs, exported reports, and generated images.
- **Tech:** MinIO (S3 API compatible).
- **Ports:** `9000` (API), `9001` (Console UI).
- **Data:** Persisted via Docker volume `minio_data`.

### 6. Redis + Celery (Task Queue)

- **Role:** Async processing for long-running tasks — AI model inference, report generation, batch operations.
- **Tech:** Redis (message broker), Celery (task worker).
- **Port:** `6379`
- **Pattern:** The API submits tasks to Celery via Redis; workers pick them up and update status in PostgreSQL.

### 7. Keycloak (Authentication & Authorization)

- **Role:** Centralized OIDC/OAuth2 identity provider with SSO, RBAC, user federation.
- **Tech:** Keycloak with PostgreSQL backend.
- **Port:** `8080`
- **Config:** `infra/keycloak/` — realm export and theme customization.
- **Flow:** Frontend initiates OIDC authorization code flow → Keycloak issues JWT → Backend validates tokens via middleware.

---

## Data Flow

```
User Uploads Drawing
        │
        ▼
┌───────────────┐
│   Frontend    │  File upload via multipart POST
│  (React SPA)  │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│    Caddy      │  Reverse proxy, TLS termination
└───────┬───────┘
        │
        ▼
┌───────────────┐     ┌───────────┐
│   Backend     │────▶│   MinIO   │  Store original file
│  (FastAPI)    │     └───────────┘
└───────┬───────┘
        │
        ▼
┌───────────────────┐
│  AI Vision Model  │  Extract quantities from drawing
│  (LLaVA / GPT-4V) │  Identify walls, floors, ceilings
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ Quantity Extractor│  Parse AI output → structured
│  (Python service) │  line items with dimensions
└───────┬───────────┘
        │
        ▼
┌───────────────────┐     ┌────────────┐
│  Material Matcher │────▶│ PostgreSQL │  Map items to cost
│  (pgvector + RAG) │     │ + pgvector  │  database entries
└───────┬───────────┘     └────────────┘
        │
        ▼
┌───────────────────┐
│ Cost Calculator   │  Apply rates, waste factors,
│                   │  labor markup → total cost
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│   BOQ Generator   │  Generate Bill of Quantities
│  (PDF / Excel)    │  with itemized breakdown
└───────┬───────────┘
        │
        ▼
┌───────────────┐
│   Frontend    │  Display BOQ, allow editing,
│  (React SPA)  │  export as PDF/Excel
└───────────────┘
```

---

## Tech Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| **FastAPI over Flask/Django** | Async-native, auto-generated OpenAPI docs, Pydantic integration, excellent performance for I/O-bound AI workloads. |
| **PostgreSQL + pgvector** | Single database for relational data + vector similarity search for material matching — no need for a separate vector DB. |
| **MinIO over cloud S3** | Full S3 API compatibility for local development; swap to AWS S3/GCS in production without code changes. |
| **Celery + Redis** | Mature, battle-tested async task queue; separates AI inference from request-response cycle. |
| **Keycloak over Supabase Auth** | Self-hosted, fine-grained RBAC, OIDC standard, realm export/import for declarative configuration. |
| **Caddy over Nginx** | Auto HTTPS, simpler config syntax, built-in Let's Encrypt integration, statically linked binary. |
| **Vite over CRA/Next.js** | Faster dev server, native ESM, simpler static export for the SPA use case. |
| **Ruff over Flake8/Black** | 10-100x faster Python linting and formatting, single dependency, pyproject.toml support. |

---

## Security Model

1. **Authentication:** OIDC authorization code flow via Keycloak.
2. **Authorization:** JWT tokens validated by backend middleware; RBAC roles (admin, estimator, viewer) defined in Keycloak realm.
3. **Transport:** All external traffic goes through Caddy with TLS. Internal container communication is over a dedicated Docker network.
4. **File Upload Security:**
   - File type validation (CAD/PDF only).
   - Size limits enforced at Caddy and FastAPI.
   - Scanned for malware (ClamAV integration optional).
   - Stored in MinIO with pre-signed URLs.
5. **Secrets:** Managed via environment variables; `.env` files only for local dev; secrets injected via Docker secrets or vault in production.
6. **API Security:**
   - Rate limiting at Caddy.
   - CORS restricted to frontend origin in production.
   - Input validation via Pydantic schemas.
7. **Database:** Runs on isolated network; no port exposure to host in production.

---

## Directory Structure Map

```
auto-cost-engine/
│
├── backend/                     # Python FastAPI application
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── api/                 # API route handlers
│   │   │   ├── __init__.py
│   │   │   ├── auth.py          # Authentication endpoints
│   │   │   ├── projects.py      # Project CRUD
│   │   │   ├── extraction.py    # Quantity extraction endpoints
│   │   │   ├── boq.py           # BOQ generation endpoints
│   │   │   └── materials.py     # Material catalog endpoints
│   │   ├── core/                # Core configuration
│   │   │   ├── config.py        # App settings
│   │   │   ├── security.py      # JWT validation, RBAC
│   │   │   └── dependencies.py  # FastAPI dependency injection
│   │   ├── models/              # SQLAlchemy ORM models
│   │   ├── schemas/             # Pydantic schemas
│   │   └── services/            # Business logic
│   │       ├── ai_service.py    # AI vision inference
│   │       ├── extraction.py    # Quantity extraction logic
│   │       ├── costing.py       # Cost calculation engine
│   │       └── export.py        # PDF/Excel export
│   ├── ai_models/               # AI model artifacts
│   ├── alembic/                 # Database migrations
│   ├── tests/                   # Pytest test suite
│   ├── uploads/                 # Uploaded file storage (dev)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── pyproject.toml
│
├── frontend/                    # React + Vite SPA
│   ├── src/                     # Application source
│   │   ├── components/          # React components
│   │   ├── pages/               # Page views
│   │   ├── hooks/               # Custom React hooks
│   │   ├── services/            # API client
│   │   ├── stores/              # State management
│   │   ├── types/               # TypeScript types
│   │   └── utils/               # Utility functions
│   ├── public/                  # Static assets
│   ├── tests/                   # Playwright E2E tests
│   ├── Dockerfile
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
│
├── infra/                       # Infrastructure configs
│   ├── Caddyfile                # Caddy reverse proxy config
│   ├── docker-compose.yml       # Infra-only compose override
│   ├── keycloak/                # Keycloak realm + themes
│   │   └── realm-export.json
│   └── postgres/                # PostgreSQL init scripts
│       └── init.sql
│
├── docs/                        # Documentation
│   └── architecture.md          # This file
│
├── .github/
│   └── workflows/
│       └── ci.yml               # CI/CD pipeline
│
├── docker-compose.yml           # Multi-service orchestration
├── Makefile                     # Convenience commands
├── .env.example                 # Environment variable template
├── .pre-commit-config.yaml      # Pre-commit hooks
└── README.md                    # Project overview & quick start
```
