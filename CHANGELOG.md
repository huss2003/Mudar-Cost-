# Changelog

## v1.0.0 (2026-07-22)

### Added

#### Drawing Intelligence Engine
- DXF parsing with layer extraction, entity type classification, text detection, and bounding box computation
- PDF parsing for text extraction and table detection via `pymupdf`
- AI-assisted raster detection pipeline (MiMo v2.5 integration) for scanned drawings
- Rule-based fallback detection that works independently of AI providers
- Drawing-to-detection pipeline with file sanity checks, format validation, and sha256 deduplication
- 76 backend tests covering DXF parsing, PDF parsing, AI pipeline, and detection service

#### AI Vision & Language
- MiMo v2.5 client with streaming support, timeout handling, and structured output parsing
- DeepSeek V4 Flash client for Q&A, anomaly detection, and value engineering suggestions
- AI model routing layer with circuit breaker (3-failure threshold, 30s cooldown) and exponential backoff retry
- RAG service with pgvector embeddings for semantic search over project reference data
- AI feature service: missing BOQ detection, anomaly detection, duration prediction, value engineering
- Fallback mode: when AI is unavailable, all features degrade gracefully with clear "unavailable" status

#### Quantity Engine
- YAML-based rule system for defining quantity calculation rules per trade
- Safe formula evaluator with whitelisted math functions (no `eval` — custom parser)
- Dependency expansion engine for resolving chained quantity rules
- Celery task orchestration for async quantity computation
- 270+ tests on rule engine, dependency engine, and quantity computation

#### Cost Engine & Material Selection
- Material selection with 51 materials from seed data, 16 vendors, brand intelligence
- Cost version history (CostVersion model tracks every change with diff)
- Live SSE updates for cost changes — push to frontend in real time
- Rate-based cost computation with labour, material, and wastage calculations
- Material selector with attribute-based filtering and auto-suggest

#### Document Generation
- BOQ Excel export: 4-sheet workbook (Summary, Detailed BOQ, Materials Summary, Vendor List)
- Proposal PDF: 8-page Jasfo-branded document with cover page, project summary, trade breakdown, cost summary, terms, and signature block
- Purchase list generation grouped by vendor
- Client presentation export with visual cost breakdown

#### Client Visualization
- 2D SVG viewer with zoom, pan, and layer toggle (custom React component)
- 3D Three.js viewer with finish preset selection (floor, wall, ceiling materials)
- Live SSE cost updates reflected in the 3D scene
- Drawing overlay with detected object annotations

#### Authentication & Authorization
- Keycloak OIDC integration (realm: `jasfo`)
- JWT token verification middleware with role-based access control
- Two roles: `user` (standard) and `admin` (full access)
- Login page with Keycloak SSO, AuthGuard React component for protected routes
- Token refresh handling with automatic redirect on expiry

#### Production Hardening
- Rate limiting: 200 req/min per IP (API), 50 req/min (auth) via Caddy
- File upload validation: magic-byte detection (`python-magic`), 50 MB max file size, 10 MB per upload
- Format whitelist: `.dxf`, `.pdf`, `.png`, `.jpg`, `.jpeg`, `.tiff`
- Structured error responses (RFC 7807 Problem Details)
- Prometheus metrics: HTTP request count/duration, AI call success/failure, BOQ computation count, Celery task states, cost engine latency
- Trace ID propagation (`trace_id` UUIDv4) across HTTP → Celery → DB → AI
- Comprehensive Caddy security headers: HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy

### Infrastructure

- **Docker Compose (production):** 8 services — PostgreSQL 16 + pgvector, MinIO, Redis 7, Keycloak 25, Backend (FastAPI), Celery Worker, Frontend (React SPA), Caddy 2
- Production compose features: pinned images, healthchecks on every service, resource limits (64 MB–1024 MB depending on service), two isolated networks (internal + proxy)
- Caddy auto-TLS via Let's Encrypt with HTTP→HTTPS redirect
- Prometheus metrics endpoint (`/metrics`) and Grafana monitoring profile via `infra/docker-compose.monitoring.yml`
- Daily PostgreSQL backups to MinIO with retention: 7 daily, 4 weekly, 3 monthly
- Interactive database restore script with confirmation prompt
- Makefile with convenience targets: `prod-up`, `prod-down`, `prod-logs`, `prod-ps`, `backup`, `restore`, `doctor`, `migrate`, `seed`
- CI/CD pipeline (GitHub Actions): lint (Ruff + ESLint + Prettier), test (pytest with PostgreSQL service), migration integrity check, Docker build and push to GHCR, integration test
- Pre-commit hooks: Ruff lint+format, large file check, YAML/JSON validation, trailing whitespace fixer

### Testing

- **271 backend pytest tests passing**, 13 skipped (require live PostgreSQL)
- Test modules: rule engine (62), cost engine (48), dependency engine (35), drawing service (76), AI contracts (28), AI features (22), material selector (18), export service (24), health endpoints (12), DB integrity (10), MiMo client (8), DeepSeek client (8)
- Frontend TypeScript compiles with zero errors
- Playwright E2E test suite covering full user journey: login → upload → detect → compute → visualize → select material → view cost → export
- Load test (k6) for quantity computation endpoint at 50 concurrent users
- Migration chain integrity verified: downgrade → upgrade → verify for all 7 migrations
- Seed data verification script: validates all 51 materials, 16 vendors, 10 labour rates, 36 productivity entries

### Configuration & Data

- All secrets and environment variables required at startup — no insecure defaults
- `.env.example` documents all 30+ environment variables with descriptions
- `scripts/doctor.py` pre-flight checker validates env vars, PostgreSQL, Redis, MinIO, Keycloak, and Celery connectivity
- Seed data: 51 materials across 10 categories, 16 vendors with GSTIN, 10 labour rates, 36 productivity entries, 10 wastage rules, 48 company standards
- Ground truth dataset: GU Office interior fit-out (13 trades, 151 items, ₹62,51,940 grand total)
- Training loop converged in 1 iteration against GU Office ground truth
- Rate history logged per change — full audit trail for cost modifications

### Upgrading from v0.x

This is the initial public release — no upgrade path from previous versions.

---

**Full commit history available at:**
`git log v1.0.0`
