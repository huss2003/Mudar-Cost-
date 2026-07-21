# AI-Powered Automatic Quantity Calculation & Cost Estimation Engine

**Intelligent interior fit-out project cost estimation from CAD/PDF drawings**

An end-to-end pipeline that ingests CAD drawings and PDF specifications, uses AI vision models to extract quantities, maps materials to a cost database, and generates detailed Bill of Quantities (BOQ) reports — all through a modern web interface.

---

## Architecture Overview

```
┌──────────┐    ┌─────────┐    ┌──────────┐
│ Frontend │───▶│  Caddy  │───▶│ Backend  │
│ (Vite +  │    │ (Proxy) │    │ (FastAPI)│
│  React)  │    └────┬────┘    └────┬─────┘
└──────────┘         │              │
                     │              ├──▶ PostgreSQL + pgvector
                     │              ├──▶ MinIO (S3)
                     │              ├──▶ Redis/Celery
                     │              └──▶ Keycloak (Auth)
                     │
                ┌────┴────┐
                │ Keycloak│
                │  (OIDC) │
                └─────────┘
```

---

## Tech Stack

| Service        | Technology                | Purpose                                    |
|----------------|---------------------------|--------------------------------------------|
| **Frontend**   | React 18 + Vite + TS      | Modern SPA with Tailwind CSS               |
| **Backend**    | Python 3.12 + FastAPI      | REST API with async endpoints              |
| **Database**   | PostgreSQL 16 + pgvector   | Relational data + vector embeddings        |
| **Object Store** | MinIO                  | S3-compatible CAD/PDF file storage         |
| **Task Queue** | Redis + Celery             | Async AI inference & report generation     |
| **Auth**       | Keycloak (OIDC/OAuth2)     | SSO, RBAC, JWT tokens                      |
| **Reverse Proxy** | Caddy                  | TLS termination, routing, static serving   |
| **Container**  | Docker + Docker Compose    | Local dev & production deployment          |

---

## Prerequisites

- **Docker** 24+ and **Docker Compose** v2 (recommended path)
- **Python** 3.12+ (for local development without Docker)
- **Node.js** 20+ (for frontend development)
- **Make** (for convenience commands)

---

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url>
cd auto-cost-engine

# 2. Copy environment configuration
cp .env.example .env

# 3. Start all services (Docker Compose)
make up

# Or manually:
docker compose up -d --build

# 4. Access the application
#    Frontend:  http://localhost:80
#    Backend:   http://localhost:8000
#    API Docs:  http://localhost:8000/docs

# 5. Run tests
make test
```

---

## Project Structure

```
auto-cost-engine/
├── backend/                  # Python FastAPI application
│   ├── app/                  # Application source code
│   │   ├── api/              # Route handlers / endpoints
│   │   ├── core/             # Config, security, dependencies
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   └── services/         # Business logic layer
│   ├── ai_models/            # AI vision & extraction models
│   ├── alembic/              # Database migrations
│   ├── tests/                # Test suite
│   ├── uploads/              # Uploaded CAD/PDF files
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                 # React + Vite SPA
│   ├── src/                  # Application source
│   ├── public/               # Static assets
│   ├── tests/                # Test suite (Playwright)
│   └── Dockerfile
├── infra/                    # Infrastructure configs
│   ├── Caddyfile             # Reverse proxy config
│   ├── keycloak/             # Keycloak realm config
│   └── postgres/             # PostgreSQL init scripts
├── docs/                     # Documentation
│   ├── architecture.md       # System architecture deep-dive
│   └── ...
├── .github/workflows/        # CI/CD pipelines
├── docker-compose.yml        # Multi-service orchestration
├── Makefile                  # Convenience commands
├── .env.example              # Environment variable template
└── .pre-commit-config.yaml   # Pre-commit hooks
```

---

## Environment Variables

| Variable             | Description                        | Default                    |
|----------------------|------------------------------------|----------------------------|
| `DATABASE_URL`       | PostgreSQL connection string       | `postgresql://...`         |
| `SUPABASE_URL`       | Supabase project URL (optional)    | `""`                       |
| `SUPABASE_KEY`       | Supabase API key (optional)        | `""`                       |
| `JWT_SECRET`         | JWT signing secret                 | `change-this-secret...`    |
| `CORS_ORIGINS`       | Allowed CORS origins               | `*`                        |
| `UPLOAD_DIR`         | File upload directory              | `/app/uploads`             |
| `MINIO_ROOT_USER`    | MinIO admin username               | `minioadmin`               |
| `MINIO_ROOT_PASSWORD`| MinIO admin password               | `minioadmin123`            |

See `.env.example` for the full list with documentation.

---

## API Documentation

When the backend is running, auto-generated API docs are available at:

- **Swagger UI:** [`http://localhost:8000/docs`](http://localhost:8000/docs)
- **ReDoc:** [`http://localhost:8000/redoc`](http://localhost:8000/redoc)

---

## Development Commands

```bash
make up              # Start all services
make down            # Stop all services
make build           # Rebuild images
make logs            # Tail all logs
make test            # Run all tests
make lint            # Run linters
make clean           # Remove containers and volumes
make migrate         # Run database migrations
make shell-backend   # Open a shell in the backend container
make shell-db        # Open psql in the database container
```

---

## License

Proprietary — all rights reserved.
