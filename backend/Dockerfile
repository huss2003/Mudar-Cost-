# =============================================================================
# Auto Cost Engine — Backend Production Dockerfile
# =============================================================================
# Multi-stage build: builder (deps) → runtime (slim, non-root).
# Shared image for both the FastAPI server and Celery worker.
# =============================================================================

# Stage 1 — Build dependencies
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies for psycopg2 and other C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --user -r requirements.txt

# Stage 2 — Runtime
# -----------------------------------------------------------------------------
FROM python:3.12-slim

# Create non-root app user
RUN groupadd -r app && useradd -r -g app app

# Runtime system deps (libpq5 for psycopg2, curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code and entrypoint script
COPY . .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Switch to non-root user
USER app

# Expose FastAPI default port
EXPOSE 8000

# Health check (only relevant for API server mode)
HEALTHCHECK --interval=15s --timeout=10s --retries=5 --start-period=30s \
  CMD curl -f http://localhost:8000/health || exit 1

# Entrypoint runs migrations, then executes the CMD
ENTRYPOINT ["docker-entrypoint.sh"]

# Default: start the FastAPI server (Celery worker overrides CMD in compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
