#!/bin/sh
# =============================================================================
# Auto Cost Engine — Docker Entrypoint
# =============================================================================
# Runs database migrations on every startup (idempotent), then executes the
# main command. This allows the same image to serve as both the API server
# (default CMD) and the Celery worker (overridden CMD in compose).
# =============================================================================
set -e

echo "[entrypoint] Running database migrations..."
alembic upgrade head
echo "[entrypoint] Migrations complete."

echo "[entrypoint] Starting: $@"
exec "$@"
