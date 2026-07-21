# Auto Cost Engine — Operations Runbook

**Version:** v1.0.0
**Updated:** 2026-07-22

## Architecture

The system consists of 8 Docker containers running on a single host behind Caddy reverse proxy with automatic TLS via Let's Encrypt:

```
┌─────────┐    ┌──────────┐    ┌───────────────────┐
│ Browser │───▶│  Caddy   │───▶│ Backend (FastAPI) │
│ (HTTPS) │    │ :443/80  │    │     :8000         │
└─────────┘    └────┬─────┘    └────────┬──────────┘
                     │                  │
                     │            ┌─────┴──────┐
                     │            │ PostgreSQL │
                     │            │  +pgvector │
                     │            └────────────┘
                     │            ┌────────────┐
                     │            │   MinIO    │
                     │            │  (S3 OSS)  │
                     │            └────────────┘
                     │            ┌────────────┐
                     │            │   Redis    │
                     │            │  (Cache +  │
                     │            │  Broker)   │
                     │            └────────────┘
                     │            ┌──────────────┐
                     │            │  Keycloak    │
                     │            │  (OIDC Auth) │
                     │            └──────────────┘
                     │            ┌───────────────┐
                     │            │ Celery Worker │
                     │            │  (Async Job)  │
                     │            └───────────────┘
                     │            ┌───────────────┐
                     │            │  Frontend     │
                     │            │  (React SPA)  │
                     │            └───────────────┘
```

### Network topology

| Network | Services | Access |
|---------|----------|--------|
| `prod-network` (internal) | postgres, minio, redis, keycloak, backend, celery-worker | Internal only, no exposed ports |
| `proxy-network` (public) | caddy, backend, frontend, keycloak | Caddy exposes :80/:443 externally |

### Data volumes

| Volume | Container | Persistence |
|--------|-----------|-------------|
| `pgdata` | postgres | Critical — daily backups to MinIO |
| `minio_data` | minio | Important — contains uploaded drawings |
| `redis_data` | redis | Non-critical — can be rebuilt |
| `caddy_data` | caddy | Let's Encrypt certificates |
| `caddy_config` | caddy | Caddy config state |

---

## Quick Start

### Prerequisites
- Docker Engine 24+ and Docker Compose v2.20+
- Domain name pointed at this server's public IP (for TLS)
- `.env.prod` file in project root with all secrets

### Deploy
```bash
# Clone
git clone <repo-url> /opt/auto-cost-engine
cd /opt/auto-cost-engine

# Copy and edit production env
cp .env.example .env.prod
# Edit .env.prod — ALL values are required, no defaults

# Run pre-flight checks
make doctor

# Deploy
docker compose -f infra/docker-compose.prod.yml up -d --build

# Verify health (wait 60s for all services)
curl http://localhost/health    # → {"status":"ok"}
curl http://localhost/readyz    # → {"status":"ready","services":[...]}

# Run migrations
docker compose -f infra/docker-compose.prod.yml exec backend alembic upgrade head

# Seed reference data
docker compose -f infra/docker-compose.prod.yml exec backend python seed/run_seed.py
```

---

## Day-to-Day Operations

### Check status
```bash
docker compose -f infra/docker-compose.prod.yml ps    # list running containers
docker compose -f infra/docker-compose.prod.yml top   # running processes per service
curl http://localhost/health                           # liveness check
curl http://localhost/readyz                           # readiness (all deps healthy)
```

### View logs
```bash
# Tail all services
docker compose -f infra/docker-compose.prod.yml logs -f

# Tail a single service
docker compose -f infra/docker-compose.prod.yml logs -f backend
docker compose -f infra/docker-compose.prod.yml logs -f celery-worker
docker compose -f infra/docker-compose.prod.yml logs -f caddy

# Last N lines
docker compose -f infra/docker-compose.prod.yml logs --tail=100 backend
```

### Trace a request by trace_id
Every request carries a `trace_id` (UUIDv4) propagated across HTTP → Celery → DB → AI calls.

```bash
# Search backend logs for a trace_id
docker compose -f infra/docker-compose.prod.yml logs backend | grep "<trace_id>"

# Search Celery worker logs
docker compose -f infra/docker-compose.prod.yml logs celery-worker | grep "<trace_id>"

# Search all services
docker compose -f infra/docker-compose.prod.yml logs --tail=1000 | grep "<trace_id>"
```

### Backup
```bash
# Manual backup (requires .env.prod)
make backup
# Dumps to /tmp/ace-backups/, uploads to MinIO bucket ace-backups/daily/

# List available backups in MinIO
make list-backups

# Backup retention
# Daily: 7 days   |   Weekly: 4 weeks   |   Monthly: 3 months
```

### Restore
```bash
# List available backups
make list-backups

# Follow interactive restore
make restore FILE=daily/ace-backup-20260722-020000.sql.gz

# The script will prompt for confirmation before overwriting the database.
```

### Seed data changes (no code deploy)

Add a new material:
```bash
# Edit seed/reference/materials.yaml
# Add entry with SKU, name, unit, rate, vendor reference

# Validate
cd backend && python scripts/verify_seed.py

# Apply
cd backend && python seed/run_seed.py
```

Add a new vendor:
```bash
# Edit seed/reference/vendors.yaml
# Add entry with name, GSTIN, contact, address

# Validate
cd backend && python scripts/verify_seed.py

# Apply
cd backend && python seed/run_seed.py
```

Add a wastage rule:
```bash
# Edit seed/rules/wastage_rules.yaml

# Validate
cd backend && python scripts/verify_seed.py

# Apply (seeds all rules)
cd backend && python seed/run_seed.py
```

### Deploy a new version
```bash
git pull origin main
docker compose -f infra/docker-compose.prod.yml up -d --build
# Verify
curl -f http://localhost/health
curl -f http://localhost/readyz
```

### Rollback
```bash
git checkout <previous-tag>
docker compose -f infra/docker-compose.prod.yml up -d --build
# Previous images are pinned by digest in docker-compose.prod.yml
```

### Rotate API keys
```bash
# 1. Update .env.prod with new MIMO_API_KEY and/or DEEPSEEK_API_KEY
# 2. Restart affected services
docker compose -f infra/docker-compose.prod.yml restart backend celery-worker
# 3. Verify AI endpoints
curl http://localhost/api/v1/ai/health
```

---

## Monitoring

### Prometheus Metrics
The backend exposes a Prometheus metrics endpoint:

```bash
curl http://localhost/metrics
```

Key metrics to watch:

| Metric | Description | Alert threshold |
|--------|-------------|-----------------|
| `ace_http_requests_total` | Total HTTP requests by route/status | Spike >500% baseline |
| `ace_ai_calls_total{outcome="failed"}` | AI provider call failures | >10% in 5 min |
| `ace_boq_computed_total` | BOQ computations completed | Business throughput |
| `ace_cost_engine_duration_seconds` | Cost engine latency (histogram) | P99 >5s |
| `ace_celery_task_states` | Celery task state counts | Any task stuck in STARTED >5min |

### Grafana (optional)
Start the monitoring stack for dashboards:

```bash
make -C backend metrics-up
```

Dashboards available at `http://<host>:3001` (default credentials in `infra/docker-compose.monitoring.yml`).

### Alert thresholds

| Condition | Warning | Critical |
|-----------|---------|----------|
| AI call failure rate | >10% in 5 min | >30% in 5 min |
| Cost engine P99 duration | >5s (any in 1h) | >10s (>10 in 1h) |
| /health or /readyz non-200 | 1 failure | 3 consecutive failures |
| Disk usage | >80% | >90% |
| Container restart count | >3 in 1h | >10 in 1h |

---

## Troubleshooting

### Service crash-loops

```bash
# Check which containers are failing
docker compose -f infra/docker-compose.prod.yml ps -a

# Get logs for failing service
docker compose -f infra/docker-compose.prod.yml logs --tail=50 <service>

# Common causes:
# - Missing env vars in .env.prod
# - Database not reachable (postgres not healthy yet)
# - Port conflicts on host
```

### /readyz shows degraded (one or more services unhealthy)

Check each dependency:

```bash
# PostgreSQL
docker compose -f infra/docker-compose.prod.yml exec postgres pg_isready -U estimation

# Redis
docker compose -f infra/docker-compose.prod.yml exec redis redis-cli -a "$REDIS_PASSWORD" ping

# MinIO
docker compose -f infra/docker-compose.prod.yml exec minio curl -f http://localhost:9000/minio/health/live

# Keycloak
docker compose -f infra/docker-compose.prod.yml exec keycloak curl -f http://localhost:8080/health/ready
```

### AI calls returning errors

The system degrades gracefully — if AI is unavailable, rule-based detection paths still work. AI-derived features show "unavailable" status.

```bash
# Check AI health endpoint
curl http://localhost/api/v1/ai/health

# Check logs for API errors
docker compose -f infra/docker-compose.prod.yml logs backend | grep -i "mimo\|deepseek\|circuit_breaker"

# Rotate API keys if expired
# Update .env.prod and restart
docker compose -f infra/docker-compose.prod.yml restart backend celery-worker
```

### Celery tasks not processing

```bash
# Check worker connectivity
docker compose -f infra/docker-compose.prod.yml exec celery-worker celery -A app.celery_app inspect ping

# Check Redis broker
docker compose -f infra/docker-compose.prod.yml exec redis redis-cli -a "$REDIS_PASSWORD" INFO | grep connected_clients

# Check task queue length
docker compose -f infra/docker-compose.prod.yml exec redis redis-cli -a "$REDIS_PASSWORD" LLEN celery

# View failed tasks
docker compose -f infra/docker-compose.prod.yml logs celery-worker --tail=50 | grep -i "error\|traceback"
```

### Database issues

```bash
# Check PostgreSQL health
docker compose -f infra/docker-compose.prod.yml exec postgres pg_isready -U estimation

# Open interactive SQL shell
docker compose -f infra/docker-compose.prod.yml exec postgres psql -U estimation -d estimation

# Check connection count
docker compose -f infra/docker-compose.prod.yml exec postgres psql -U estimation -d estimation -c "SELECT count(*) FROM pg_stat_activity;"

# Verify migrations are current
docker compose -f infra/docker-compose.prod.yml exec backend alembic current

# Run pending migrations
docker compose -f infra/docker-compose.prod.yml exec backend alembic upgrade head
```

### Upload failures

Files are validated server-side before processing:

| Check | Limit |
|-------|-------|
| Max file size | 50 MB |
| Max upload per request | 10 MB |
| Allowed formats | `.dxf`, `.pdf`, `.png`, `.jpg`, `.jpeg`, `.tiff` |
| Max concurrent uploads | 10 |

If uploads fail:
1. Check file size and format
2. Check MinIO connectivity: `docker compose logs minio`
3. Check disk space: `df -h`
4. Check upload directory permissions

---

## Maintenance

### Database maintenance

```bash
# Vacuum (weekly recommended)
docker compose -f infra/docker-compose.prod.yml exec postgres psql -U estimation -d estimation -c "VACUUM ANALYZE;"

# Reindex (monthly)
docker compose -f infra/docker-compose.prod.yml exec postgres psql -U estimation -d estimation -c "REINDEX DATABASE estimation;"

# Check table sizes
docker compose -f infra/docker-compose.prod.yml exec postgres psql -U estimation -d estimation -c "
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;"
```

### Log rotation

All services use Docker's json-file logging driver with:
- Max size: 10 MB per file
- Max files: 3 per service

### Certificate renewal

Caddy handles Let's Encrypt renewal automatically. Certificates are stored in `caddy_data` volume.
To force renewal:
```bash
docker compose -f infra/docker-compose.prod.yml exec caddy caddy renew --force
```

### Backup verification (monthly)

```bash
# 1. Create a test backup
docker compose -f infra/docker-compose.prod.yml exec -T postgres pg_dump -U estimation estimation | gzip > /tmp/test-restore.sql.gz

# 2. Start a temporary PostgreSQL container and restore
docker run --rm --network ace_prod-network \
  -e POSTGRES_DB=estimation_test \
  -e POSTGRES_USER=estimation \
  -e POSTGRES_PASSWORD=$POSTGRES_PASSWORD \
  postgres:16-alpine -c "pg_isready -U estimation"

# 3. Verify the restore
docker compose -f infra/docker-compose.prod.yml exec postgres psql -U estimation -d estimation -c "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public';"

# 4. Drop test database
docker compose -f infra/docker-compose.prod.yml exec postgres psql -U estimation -c "DROP DATABASE IF EXISTS estimation_test;"
```

---

## Incident Response

### Severity levels

| Severity | Definition | Response time |
|----------|------------|---------------|
| **P0** | Service down or data loss | Immediate |
| **P1** | Feature degraded, no workaround | 1 hour |
| **P2** | Minor issue, workaround exists | 4 hours |
| **P3** | Cosmetic / non-urgent | 24 hours |

### P0 — Hard down

1. Check if host is reachable: `ping <host>`
2. SSH and check Docker: `docker info`
3. Restart all services: `docker compose -f infra/docker-compose.prod.yml restart`
4. If host rebooted, start services: `docker compose -f infra/docker-compose.prod.yml up -d`
5. Verify health: `curl http://localhost/health`
6. **Post-mortem:** file a GitHub issue with timeline and root cause

### P1 — Feature degraded

1. Check which feature and when it broke
2. Look for recent deployments or config changes
3. Check AI provider status (if AI features affected)
4. Rollback if recent deploy is suspected: `git checkout <previous-tag>` then `docker compose up -d --build`
5. File a bug report

### Data recovery

If database is corrupted:
1. Stop all services: `docker compose -f infra/docker-compose.prod.yml down`
2. Identify a recent backup: `make list-backups`
3. Restore: `make restore FILE=<backup_path>`
4. Start services: `docker compose -f infra/docker-compose.prod.yml up -d`
5. Verify data integrity: `make -C backend verify-seed`

---

## Security

### Firewall rules

| Port | Purpose | Source |
|------|---------|--------|
| 22/tcp | SSH | Admin IPs only |
| 80/tcp | HTTP (redirect to HTTPS) | Any |
| 443/tcp | HTTPS | Any |
| 5432/tcp | PostgreSQL | Internal only (Docker network) |
| 6379/tcp | Redis | Internal only |
| 9000/tcp | MinIO API | Internal only |
| 9001/tcp | MinIO Console | Internal only |
| 8080/tcp | Keycloak | Internal only |

### Secrets management

- All secrets in `.env.prod` — never commit to git
- `.env.prod` is in `.gitignore`
- Rotate API keys quarterly
- Rotate PostgreSQL password and Keycloak admin password on major version upgrades
- JWT signing key (`SECRET_KEY`) must be at least 32 characters

### Access control

- All API requests require JWT token except `/health` and `/readyz`
- Token issued by Keycloak realm `jasfo`
- Two roles: `user` (standard) and `admin` (full access)
- Rate limiting: 200 req/min per IP on API, 50 req/min on auth
- File upload content-type validation via `python-magic`

---

## Reference

### Container images and versions

| Service | Image | Version |
|---------|-------|---------|
| PostgreSQL | `pgvector/pgvector:pg16` | 16.x |
| MinIO | `minio/minio:latest` | Latest stable |
| Redis | `redis:7-alpine` | 7.x |
| Keycloak | `quay.io/keycloak/keycloak:25.0` | 25.0 |
| Caddy | `caddy:2-alpine` | 2.x |
| Backend | Build from `backend/Dockerfile` | Python 3.12 |
| Frontend | Build from `frontend/Dockerfile` | Node 20 + Vite |

### Resource limits

| Service | Memory limit | Memory reservation | CPU |
|---------|-------------|-------------------|-----|
| postgres | 512 MB | 256 MB | Default |
| minio | 512 MB | 256 MB | Default |
| redis | 256 MB | 128 MB | Default |
| keycloak | 1024 MB | 512 MB | Default |
| backend | 512 MB | 256 MB | Default |
| celery-worker | 512 MB | 256 MB | Default |
| frontend | 256 MB | 128 MB | Default |
| caddy | 128 MB | 64 MB | Default |

### Key file paths

| Path | Purpose |
|------|---------|
| `infra/docker-compose.prod.yml` | Production compose definition |
| `infra/Caddyfile.prod` | Caddy reverse proxy config |
| `scripts/backup-db.sh` | Database backup script |
| `scripts/restore-db.sh` | Database restore script |
| `scripts/doctor.py` | Pre-flight health checker |
| `backend/seed/` | Reference data (materials, vendors, rules) |
| `infra/keycloak/realm-export.json` | Keycloak realm configuration |
| `infra/postgres/init.sql` | PostgreSQL init script |
| `.env.prod` | Production secrets (NOT in git) |
