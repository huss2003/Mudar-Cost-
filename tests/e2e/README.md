# Auto Cost Engine — E2E Tests

Playwright-based end-to-end tests covering the complete user journey through
the Auto Cost Engine web application.

## Test Coverage

The full journey covers **10 steps**:

| # | Step | Description |
|---|------|-------------|
| 1 | Login | Keycloak OIDC auth → redirect to app |
| 2 | Upload DXF | Upload `sample_floor_plan.dxf` → wait for Celery processing |
| 3 | View Objects | Click drawing → 2D viewer loads detected objects |
| 4 | Compute BOQ | Dispatch Celery task → poll until BOQ items appear |
| 5 | 3D Viewer | Navigate to Quantities → verify Three.js canvas + finish presets |
| 6 | Select Material | Fetch BOQ item materials → assign to item |
| 7 | AI Ask | POST `/projects/{id}/ask` with question about the project |
| 8 | Anomalies | POST `/projects/{id}/anomalies` detect cost/quantity outliers |
| 9 | Proposal | Generate PDF proposal → verify `%PDF-` header |
| 10 | Logout | Click Sign out → verify redirect to `/login` |

## Prerequisites

- **Node.js 20+** with npm
- **Docker Compose stack** running all 8 services:

  ```bash
  cd auto-cost-engine
  make up        # docker compose -f infra/docker-compose.yml up -d --build
  make seed      # python backend/seed/run_seed.py (loads rules & materials)
  ```

- **Keycloak realm imported** (done automatically via `--import-realm` in
  `docker-compose.yml`).  Test user credentials:

  - Username: `test@jasfo.com`
  - Password: `test1234`

- **Frontend accessible** at `http://localhost:5173` (Vite dev server runs
  inside Docker and is proxied through Caddy on port 80, but tests default
  to port 5173 which has the `/api` proxy configured).

## Setup

```bash
cd tests/e2e
npm install
npx playwright install chromium
```

## Running Tests

```bash
# Default (headless)
npx playwright test

# Headed mode (watch the browser)
HEADED=1 npx playwright test

# Single test file
npx playwright test full-journey.spec.ts

# Specific step (by grep)
npx playwright test -g "Login"

# Debug mode (step-by-step with inspector)
npx playwright test --debug

# Generate Playwright report (after run)
npx playwright show-report
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_URL` | `http://localhost:5173` | Frontend URL (Vite dev server) |
| `KEYCLOAK_URL` | `http://localhost:8080` | Keycloak base URL |
| `KEYCLOAK_USER` | `test@jasfo.com` | Keycloak test user |
| `KEYCLOAK_PASS` | `test1234` | Keycloak test password |
| `HEADED` | — | Set to `1` for headed mode |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_USER` | `estimation` | PostgreSQL user |
| `DB_PASS` | `estimation_secret_2024` | PostgreSQL password |

## Project Structure

```
tests/e2e/
├── playwright.config.ts    # Playwright configuration
├── package.json            # Node dependencies
├── .gitignore              # Ignored files
├── README.md               # This file
├── helpers.ts              # Shared test utilities (auth, API, DB)
├── full-journey.spec.ts    # Full user journey E2E test
└── playwright-report/      # Generated test report (after run)
```

## Recording Tests

```bash
cd tests/e2e
npx playwright codegen http://localhost:5173
```

## Troubleshooting

**Frontend not reachable:**
```bash
# Check containers
docker compose -f infra/docker-compose.yml ps

# Check logs
docker compose -f infra/docker-compose.yml logs frontend
docker compose -f infra/docker-compose.yml logs caddy
```

**Keycloak not ready:**
```bash
# Keycloak takes ~30-60s to start on first run
docker compose -f infra/docker-compose.yml logs keycloak | tail -20
```

**Database seed not run:**
```bash
cd backend && python seed/run_seed.py
```
