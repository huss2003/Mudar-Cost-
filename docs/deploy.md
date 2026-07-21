# Auto Cost Engine — Production Deployment Runbook

## 1. Overview

This document describes the full procedure for deploying the **Auto Cost Engine**
to a production environment. The stack runs on a single Docker host behind a
Caddy reverse proxy with automatic TLS via Let's Encrypt.

**Stack diagram:**

```
Internet ──► [Caddy :80/:443] ──┬──► Backend (:8000) ──┬──► PostgreSQL (:5432)
                                │                       ├──► Redis (:6379)
                                │                       └──► MinIO (:9000)
                                ├──► Frontend (:5173)
                                └──► Keycloak (:8080) ──┘
```

---

## 2. Prerequisites

| Requirement          | Minimum                         | Recommended                     |
|----------------------|---------------------------------|---------------------------------|
| CPU                  | 2 cores                         | 4 cores                         |
| RAM                  | 4 GB                            | 8 GB                            |
| Disk                 | 20 GB SSD                       | 50 GB SSD                       |
| Docker               | 24.x + Docker Compose 2.x       | Latest stable                   |
| Domain               | A/AAAA record pointing to host  | Valid DNS with short TTL        |
| Firewall             | Ports 80/tcp, 443/tcp open      | All other ports closed          |
| OS                   | Ubuntu 22.04 / Debian 12        | Ubuntu 24.04 LTS                |

### 2.1 Install Docker

```bash
# Ubuntu / Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

### 2.2 Verify Docker Compose

```bash
docker compose version
# Expected: Docker Compose v2.x
```

### 2.3 Configure Firewall

```bash
# ufw
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 2.4 Set Up DNS

Create an A record pointing your domain (e.g. `app.example.com`) to the
server's public IP address. Optionally, create a CNAME for auth:
`auth.example.com → app.example.com`.

---

## 3. Initial Deployment

### 3.1 Clone Repository

```bash
git clone https://github.com/jasfo/auto-cost-engine.git
cd auto-cost-engine
```

### 3.2 Configure Production Secrets

```bash
cp .env.example .env.prod
nano .env.prod   # ⚠️ Edit all secrets!
```

**Required variables in `.env.prod`:**

```ini
# PostgreSQL
POSTGRES_PASSWORD=<generate-a-strong-password>

# MinIO
MINIO_ROOT_USER=ace_admin
MINIO_ROOT_PASSWORD=<generate-a-strong-password>
MINIO_BUCKET=drawings

# Redis
REDIS_PASSWORD=<generate-a-strong-password>

# Keycloak
KEYCLOAK_ADMIN_PASSWORD=<generate-a-strong-password>
KEYCLOAK_HOSTNAME=auth.yourdomain.com

# Database URL (asyncpg — update password)
DATABASE_URL=postgresql+asyncpg://estimation:${POSTGRES_PASSWORD}@postgres:5432/estimation

# MinIO connection
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=${MINIO_ROOT_USER}
MINIO_SECRET_KEY=${MINIO_ROOT_PASSWORD}

# Redis
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0

# Keycloak OpenID Connect
KEYCLOAK_URL=http://keycloak:8080
KEYCLOAK_REALM=jasfo
KEYCLOAK_CLIENT_ID=estimation-web

# Celery
CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/1
CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@redis:6379/2

# External API Keys (set these)
MIMO_API_KEY=<your-mimo-api-key>
DEEPSEEK_API_KEY=<your-deepseek-api-key>

# Caddy / Domain
DOMAIN=app.yourdomain.com
ACME_EMAIL=admin@yourdomain.com
```

> **Security note**: Use a password manager to generate 32+ character random
> strings for each secret. Never commit `.env.prod` to version control.

### 3.3 Start the Stack

```bash
# Pull images and start all services
docker compose -f infra/docker-compose.prod.yml up -d

# Watch the startup
docker compose -f infra/docker-compose.prod.yml logs -f
```

Wait for all services to show "healthy" in:

```bash
docker compose -f infra/docker-compose.prod.yml ps
```

Expected output:

```
NAME                   STATUS
ace-caddy              Up 2 minutes (healthy)
ace-backend            Up 2 minutes (healthy)
ace-frontend           Up 2 minutes (healthy)
ace-postgres           Up 2 minutes (healthy)
ace-minio              Up 2 minutes (healthy)
ace-redis              Up 2 minutes (healthy)
ace-keycloak           Up 2 minutes (healthy)
ace-celery-worker      Up 2 minutes
```

---

## 4. Keycloak Setup

### 4.1 Access Keycloak Admin Console

Open `https://auth.yourdomain.com` (replace with your `KEYCLOAK_HOSTNAME`).

Log in with:
- **Username**: `admin`
- **Password**: (value from `KEYCLOAK_ADMIN_PASSWORD` in `.env.prod`)

### 4.2 Import Realm

1. In the admin console, hover over the realm name (top-left) and click
   **"Add realm"**.
2. Click **"Browse"** and select `infra/keycloak/realm-export.json`.
3. Click **"Create"**.

The realm (`jasfo`) and its clients/users are now imported.

### 4.3 Configure Client (if not imported)

If the realm import doesn't include the client:

1. Go to **Clients → Create client**.
2. Client ID: `estimation-web`
3. Client protocol: `openid-connect`
4. Root URL: `https://app.yourdomain.com`
5. Valid redirect URIs: `https://app.yourdomain.com/*`
6. Valid post logout redirect URIs: `https://app.yourdomain.com`
7. Web origins: `https://app.yourdomain.com`

### 4.4 Create Test Users

1. Go to **Users → Add user**.
2. Set username (e.g. `engineer1`), email, first/last name.
3. Go to **Credentials** tab and set a temporary password.
4. Go to **Role mapping** tab and assign appropriate roles.

---

## 5. Post-Install Verification

### 5.1 Health Endpoints

```bash
# General health check
curl https://app.yourdomain.com/health
# Expected: {"status":"ok","version":"0.1.0"}

# Full API health (but this won't have auth token for most endpoints)
curl -I https://app.yourdomain.com/api/v1/
```

### 5.2 Celery Worker Health

```bash
curl https://app.yourdomain.com/api/v1/celery/health
# Expected: {"status":"ok","active_workers":[...]}
```

### 5.3 Frontend Access

Open `https://app.yourdomain.com` in a browser. You should see the login
page redirecting to Keycloak.

### 5.4 Verify TLS Certificate

```bash
echo | openssl s_client -connect app.yourdomain.com:443 -servername app.yourdomain.com 2>/dev/null | openssl x509 -noout -subject -issuer -dates
```

### 5.5 Check Logs

```bash
docker compose -f infra/docker-compose.prod.yml logs --tail=50 -f
```

---

## 6. Backup Strategy

### 6.1 Automated Database Backups

A backup script (`scripts/backup-db.sh`) dumps the PostgreSQL database,
compresses it with gzip, and uploads it to MinIO.

**Schedule the backup via cron:**

```bash
# Edit crontab
crontab -e

# Run daily at 02:00 UTC
0 2 * * * /home/user/auto-cost-engine/scripts/backup-db.sh >> /var/log/ace-backup.log 2>&1
```

### 6.2 Retention Policy

| Backup Type | Retention | Schedule     | Location                          |
|-------------|-----------|--------------|-----------------------------------|
| Daily       | 7 days    | Every 24h    | `ace-minio/ace-backups/daily/`    |
| Weekly      | 4 weeks   | Every Sunday | `ace-minio/ace-backups/weekly/`   |
| Monthly     | 3 months  | 1st of month | `ace-minio/ace-backups/monthly/`  |

### 6.3 Manual Backup

```bash
make backup
```

Or directly:

```bash
docker compose -f infra/docker-compose.prod.yml exec postgres pg_dump -U estimation -d estimation | gzip > /tmp/ace-manual-$(date +%Y%m%d-%H%M%S).sql.gz
```

### 6.4 Restore from Backup

```bash
make restore FILE=ace-backup-20260101-020000.sql.gz
```

---

## 7. Monitoring

### 7.1 Uptime Monitoring (Recommended)

Set up **Uptime Kuma** or similar to monitor:

| Endpoint                              | Expected Status |
|---------------------------------------|-----------------|
| `https://app.yourdomain.com/health`   | 200 OK          |
| `https://app.yourdomain.com`          | 200 OK          |

### 7.2 View Logs

```bash
# All services
docker compose -f infra/docker-compose.prod.yml logs -f

# Specific service
docker compose -f infra/docker-compose.prod.yml logs -f backend

# Last N lines
docker compose -f infra/docker-compose.prod.yml logs --tail=100 backend
```

### 7.3 Resource Usage

```bash
# Container resource usage
docker stats

# Disk usage
docker system df
df -h
```

### 7.4 MinIO Console

Access MinIO admin at `https://app.yourdomain.com/minio-console` with the
`MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` credentials from `.env.prod`.

---

## 8. Scaling

### 8.1 Multiple Backend Replicas

```bash
docker compose -f infra/docker-compose.prod.yml up -d --scale backend=3
```

> **Note**: When scaling the backend, ensure the in-memory rate limiter is
> replaced with a Redis-backed limiter (see `app/services/rate_limiter.py`).
> The application currently uses an in-memory limiter that is **not**
> shared between replicas.

### 8.2 Celery Worker Auto-Scaling

```bash
docker compose -f infra/docker-compose.prod.yml up -d --scale celery-worker=2
```

### 8.3 Redis for Rate Limiting

For multi-replica deployments, configure the backend to use Redis for
distributed rate limiting by setting:

```ini
RATE_LIMIT_BACKEND=redis
```

---

## 9. Maintenance

### 9.1 Update the Stack

```bash
# Pull latest images
docker compose -f infra/docker-compose.prod.yml pull

# Rebuild and restart
docker compose -f infra/docker-compose.prod.yml up -d --build

# Prune old images
docker image prune -f
```

### 9.2 Run Database Migrations

```bash
docker compose -f infra/docker-compose.prod.yml exec backend alembic upgrade head
```

### 9.3 Seed Reference Data

```bash
docker compose -f infra/docker-compose.prod.yml exec backend python seed/run_seed.py
```

---

## 10. Troubleshooting

### 10.1 TLS Certificate Issues

```bash
# Check Caddy logs
docker compose -f infra/docker-compose.prod.yml logs caddy

# Verify DNS resolves correctly
dig +short app.yourdomain.com
```

### 10.2 Container Won't Start

```bash
# Check logs
docker compose -f infra/docker-compose.prod.yml logs <service-name>

# Inspect health
docker inspect ace-<service> | jq '.[].State.Health'
```

### 10.3 Database Connection Refused

```bash
# Check Postgres is healthy
docker compose -f infra/docker-compose.prod.yml ps postgres

# Try connecting directly
docker compose -f infra/docker-compose.prod.yml exec postgres psql -U estimation -d estimation -c "SELECT 1;"
```

### 10.4 Keycloak Not Starting

```bash
# Check if database migration failed
docker compose -f infra/docker-compose.prod.yml logs keycloak | grep ERROR

# Verify Postgres has the keycloak database
docker compose -f infra/docker-compose.prod.yml exec postgres psql -U estimation -l | grep keycloak
```

### 10.5 Disk Space Low

```bash
# Prune unused Docker data
docker system prune -af

# Check backup usage in MinIO (via mc client or console)
```

---

## 11. Rollback

### 11.1 Revert to Previous Docker Images

```bash
# Tag the current images before updating
docker tag ace-backend:latest ace-backend:pre-update

# If update fails, roll back
docker compose -f infra/docker-compose.prod.yml down
# Edit docker-compose.prod.yml to pin the previous image tag
docker compose -f infra/docker-compose.prod.yml up -d
```

### 11.2 Database Rollback

```bash
# If a migration caused issues
docker compose -f infra/docker-compose.prod.yml exec backend alembic downgrade -1

# Restore from backup if needed
make restore FILE=<last-good-backup>.sql.gz
```

---

## 12. Security Checklist

- [ ] All secrets in `.env.prod` are strong random passwords
- [ ] `.env.prod` is in `.gitignore`
- [ ] Firewall allows only ports 80/tcp and 443/tcp from the internet
- [ ] SSH uses key-based authentication only
- [ ] Docker daemon is not exposed on TCP
- [ ] TLS certificate is valid (check via Let's Debug or SSL Labs)
- [ ] HSTS header is configured (preload-ready)
- [ ] Keycloak admin password is strong and rotated regularly
- [ ] MinIO console is behind Caddy (not exposed directly)
- [ ] Database backups are tested with a restore at least monthly
- [ ] System updates are applied promptly
- [ ] Docker images are regularly rebuilt for security patches
- [ ] Logging is in JSON format for log aggregation compatibility
- [ ] Rate limiting is enabled on API and auth routes
