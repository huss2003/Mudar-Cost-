.PHONY: help install dev-install test lint format clean migrate seed verify-seed run

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	pip install -r requirements.txt

dev-install: ## Install dev dependencies
	pip install -r requirements-dev.txt
	pip install -e .

test: ## Run tests
	python -m pytest tests/ -v --tb=short $(ARGS)

lint: ## Run linters
	ruff check app/ seed/ tests/ scripts/ --fix
	ruff format app/ seed/ tests/ scripts/ --check

format: ## Auto-format code
	ruff format app/ seed/ tests/ scripts/

clean: ## Clean build artifacts
	rm -rf .pytest_cache __pycache__ .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

migrate: ## Run Alembic migrations
	alembic upgrade head

seed: ## Run seed data loader
	python seed/run_seed.py

verify-seed: ## Validate seed data integrity
	@python scripts/verify_seed.py

run-dev: ## Run development server
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run: ## Run production server
	uvicorn app.main:app --host 0.0.0.0 --port 8000

.PHONY: metrics-up metrics-down
metrics-up: ## Start Prometheus + Grafana monitoring stack
	docker compose -f infra/docker-compose.monitoring.yml up -d

metrics-down: ## Stop monitoring stack
	docker compose -f infra/docker-compose.monitoring.yml down
