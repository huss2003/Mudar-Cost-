.PHONY: up down logs restart ps clean test seed migrate db-shell shell doctor
.PHONY: prod-up prod-down prod-logs prod-ps prod-restart backup restore
.PHONY: prod-backup prod-restore list-backups

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

# Docker Compose file paths
COMPOSE_FILE = infra/docker-compose.yml
PROD_COMPOSE_FILE = infra/docker-compose.prod.yml

# Start all dev services
up:
	docker compose -f $(COMPOSE_FILE) up -d --build

# Stop all dev services
down:
	docker compose -f $(COMPOSE_FILE) down

# Follow logs from all services
logs:
	docker compose -f $(COMPOSE_FILE) logs -f

# Restart all services
restart: down up

# Show running service status
ps:
	docker compose -f $(COMPOSE_FILE) ps

# Stop and remove all volumes (full cleanup)
clean:
	docker compose -f $(COMPOSE_FILE) down -v

# Run backend tests
test:
	cd backend && python -m pytest

# Run database migrations
migrate:
	cd backend && alembic upgrade head

# Rollback last migration
migrate-down:
	cd backend && alembic downgrade -1

# Seed reference data (rules, materials, vendors)
seed:
	cd backend && python seed/run_seed.py

# Open database shell (requires docker compose running)
db-shell:
	docker compose -f $(COMPOSE_FILE) exec postgres psql -U estimation -d estimation

# Open backend Python shell
shell:
	cd backend && python -c "from app.database import engine; print('Database engine ready:', engine)"

# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

.PHONY: smoke
smoke: ## Run smoke tests against the deployed stack
	SMOKE_BASE_URL=http://localhost python scripts/smoke_test.py

.PHONY: smoke-prod
smoke-prod: ## Run smoke tests against the production stack
	SMOKE_BASE_URL=https://ace.example.com python scripts/smoke_test.py

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

doctor: ## Run pre-flight checks (env vars, services)
	@python scripts/doctor.py

# ---------------------------------------------------------------------------
# Database Integrity
# ---------------------------------------------------------------------------

.PHONY: check-migrations
check-migrations: ## Run alembic downgrade+upgrade to verify migration chain
	cd backend && alembic downgrade base && alembic upgrade head

.PHONY: check-fks
check-fks: ## Validate all FK constraints and pgvector extension via pytest
	cd backend && python -m pytest tests/test_db_integrity.py -v --tb=short

# ---------------------------------------------------------------------------
# Production
# ---------------------------------------------------------------------------

# Start all production services
prod-up:
	docker compose -f $(PROD_COMPOSE_FILE) up -d --build

# Stop all production services
prod-down:
	docker compose -f $(PROD_COMPOSE_FILE) down

# Follow production logs
prod-logs:
	docker compose -f $(PROD_COMPOSE_FILE) logs -f

# Show production service status
prod-ps:
	docker compose -f $(PROD_COMPOSE_FILE) ps

# Restart production services
prod-restart: prod-down prod-up

# Pull latest images for production
prod-pull:
	docker compose -f $(PROD_COMPOSE_FILE) pull

# Run database backup (requires .env.prod loaded)
backup:
	@echo "=== Running database backup ==="
	@if [ ! -f .env.prod ]; then echo "ERROR: .env.prod not found!"; exit 1; fi
	@export $$(grep -v '^\s*#' .env.prod | grep -v '^\s*$$' | xargs) && \
		./scripts/backup-db.sh

# Trigger a manual backup via the backup cron container
prod-backup:
	@echo "=== Triggering manual backup via cron container ==="
	docker compose -f $(PROD_COMPOSE_FILE) exec -T db-backup /usr/local/bin/backup-db.sh

# Restore database from latest backup in MinIO
# Usage: make prod-restore FILE=ace-backup-20260101-020000.sql.gz
prod-restore:
	@echo "=== Restoring database from backup ==="
	@if [ -z "$(FILE)" ]; then echo "ERROR: Specify FILE=backup-filename"; echo "  List available backups: make list-backups"; exit 1; fi
	@echo "Downloading $(FILE) from MinIO..."
	@docker compose -f $(PROD_COMPOSE_FILE) exec -T minio sh -c "mc cat data/ace-backups/daily/$(FILE) 2>/dev/null || mc cat data/ace-backups/weekly/$(FILE) 2>/dev/null || mc cat data/ace-backups/monthly/$(FILE) 2>/dev/null" | gunzip | docker compose -f $(PROD_COMPOSE_FILE) exec -T postgres psql -U estimation -d estimation 2>&1 || echo "ERROR: Backup file not found. Use make list-backups to see available files."

# Restore database from a backup file
# Usage: make restore FILE=ace-backup-20260101-020000.sql.gz
restore:
	@echo "=== Restoring database from backup ==="
	@if [ ! -f .env.prod ]; then echo "ERROR: .env.prod not found!"; exit 1; fi
	@if [ -z "$(FILE)" ]; then echo "ERROR: Specify FILE=backup-filename"; exit 1; fi
	@export $$(grep -v '^\s*#' .env.prod | grep -v '^\s*$$' | xargs) && \
		./scripts/restore-db.sh "$(FILE)"

# Run production database migrations
prod-migrate:
	docker compose -f $(PROD_COMPOSE_FILE) exec backend alembic upgrade head

# Seed production database
prod-seed:
	docker compose -f $(PROD_COMPOSE_FILE) exec backend python seed/run_seed.py

# Open production database shell
prod-db-shell:
	docker compose -f $(PROD_COMPOSE_FILE) exec postgres psql -U estimation -d estimation

# List backups stored in MinIO
list-backups:
	@echo "=== Daily backups ==="
	@docker compose -f $(PROD_COMPOSE_FILE) exec -T minio mc ls data/ace-backups/daily/ 2>/dev/null || echo "  (no backups yet)"
	@echo "=== Weekly backups ==="
	@docker compose -f $(PROD_COMPOSE_FILE) exec -T minio mc ls data/ace-backups/weekly/ 2>/dev/null || echo "  (no weekly backups yet)"
	@echo "=== Monthly backups ==="
	@docker compose -f $(PROD_COMPOSE_FILE) exec -T minio mc ls data/ace-backups/monthly/ 2>/dev/null || echo "  (no monthly backups yet)"
