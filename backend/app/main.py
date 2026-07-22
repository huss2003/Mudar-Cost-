"""
FastAPI application entry-point for Auto Cost Engine.

Sets up:
- Structured logging (structlog)
- CORS
- Routers (API v1)
- Structured error responses (HTTPException, validation errors)
- Catch-all unhandled exception middleware
- In-memory IP-based rate limiter
- Request logging middleware (method, path, status, duration_ms, trace_id)
- Trace ID propagation across the request lifecycle
- Health / readiness endpoints
- Prometheus /metrics endpoint
"""

from contextlib import asynccontextmanager
from time import monotonic
from typing import AsyncIterator
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.minio_client import create_bucket_if_not_exists
from app.routers import (
    ai,
    ai_features,
    auth,
    costs,
    doc_gen,
    drawings,
    exports,
    live,
    materials,
    proposals,
    quantities,
)
from app.routers.celery_monitor import router as celery_monitor_router
from app.routers.health import router as health_router
from app.routers.metrics import router as metrics_router
from app.services.metrics import http_requests
from app.services.trace import set_trace_id

# Ensure Celery tasks are registered
import app.tasks.drawings  # noqa: F401
import app.tasks.exports  # noqa: F401
import app.tasks.quantities  # noqa: F401

# ---------------------------------------------------------------------------
# Structured logging with structlog
# ---------------------------------------------------------------------------
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer() if settings.DEBUG
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Helpers for structured error envelope
# ---------------------------------------------------------------------------

def _make_error_response(
    status_code: int,
    code: str,
    message: str,
    trace_id: str,
    hint: str | None = None,
) -> JSONResponse:
    """Build a structured error JSON response."""
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=ErrorDetail(
                trace_id=trace_id,
                code=code,
                message=message,
                hint=hint,
            ).model_dump(),
        ).model_dump(),
    )


def _get_trace_id(request: Request) -> str:
    """Retrieve the trace_id from request state (set by middleware)."""
    return getattr(request.state, "trace_id", str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Lifespan events (replaces deprecated on_event)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup / shutdown."""
    # --- startup ---
    logger.info("Starting %s …", settings.APP_NAME)
    if settings.MINIO_ENDPOINT:
        try:
            await create_bucket_if_not_exists()
        except Exception:
            logger.warning("MinIO bucket setup failed — continuing")

    # Clear any existing structlog context vars
    structlog.contextvars.clear_contextvars()

    yield

    # --- shutdown ---
    logger.info("%s shut down gracefully", settings.APP_NAME)


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

# -- CORS --
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================================================================
# Trace-ID middleware — every request gets an X-Trace-Id
# ======================================================================


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    """Attach a trace_id to every request.

    If the client sends an ``X-Trace-Id`` header, that value is honoured;
    otherwise a new UUID is generated.  The trace_id is:
    - Stored on ``request.state.trace_id`` for use in handlers
    - Bound to structlog context vars for structured logging
    - Emitted as a response header ``X-Trace-Id``
    """
    trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
    request.state.trace_id = trace_id
    with structlog.contextvars.bound_contextvars(trace_id=trace_id):
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response


# ======================================================================
# Request logging middleware — log every HTTP request + Prometheus counter
# ======================================================================


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log every HTTP request with method, path, status, duration_ms, trace_id.

    Also increments the ``ace_http_requests_total`` counter.
    """
    start = monotonic()
    response = await call_next(request)
    duration_ms = (monotonic() - start) * 1000

    route = request.url.path
    status_group = f"{response.status_code // 100}xx"
    http_requests.labels(
        method=request.method,
        route=route,
        status=status_group,
    ).inc()

    logger.info(
        "http_request",
        method=request.method,
        path=route,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 1),
        trace_id=getattr(request.state, "trace_id", ""),
    )
    return response


# ======================================================================
# Structured error responses
# ======================================================================


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Return a structured JSON body for HTTP exceptions."""
    trace_id = _get_trace_id(request)
    logger.warning(
        "HTTP %s — %s",
        exc.status_code,
        exc.detail,
        extra={"trace_id": trace_id, "status_code": exc.status_code},
    )
    return _make_error_response(
        status_code=exc.status_code,
        code=f"HTTP_{exc.status_code}",
        message=str(exc.detail),
        trace_id=trace_id,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return detailed validation errors in a consistent envelope.

    Each entry in the ``error.details`` list carries:
    - ``loc`` — the dotted path to the field that failed
    - ``msg`` — human-readable error message
    - ``type`` — error type (e.g. ``value_error.missing``)
    """
    trace_id = _get_trace_id(request)
    errors = [
        {"loc": e["loc"], "msg": e["msg"], "type": e["type"]}
        for e in exc.errors()
    ]
    logger.warning(
        "Validation failed — %d errors",
        len(errors),
        extra={"trace_id": trace_id, "validation_errors": errors},
    )
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error=ErrorDetail(
                trace_id=trace_id,
                code="VALIDATION_ERROR",
                message="Request validation failed",
                hint="Check the 'details' field for per-field errors",
            ).model_dump(),
            data={"details": errors},
        ).model_dump(),
    )


# ======================================================================
# Global catch-all exception handler
# ======================================================================


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Last-resort handler for completely unhandled exceptions.

    Logs the full traceback with trace_id and returns a generic 500 in
    the structured error envelope rather than exposing internal details
    to the client.
    """
    trace_id = _get_trace_id(request)
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        extra={"trace_id": trace_id},
    )
    return _make_error_response(
        status_code=500,
        code="INTERNAL_ERROR",
        message="An unexpected error occurred",
        trace_id=trace_id,
        hint="Contact support with this trace ID",
    )


# ======================================================================
# In-memory rate limiter middleware
# ======================================================================


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply per-IP rate limiting to all API routes.

    Limits are **per minute, per client IP**.  When exceeded the client
    receives a 429 Too Many Requests response.

    .. note::
        This is a single-process in-memory limiter.  For multi-worker or
        multi-replica deployments, replace with a Redis-backed limiter.
    """
    # Only rate-limit /api/* paths
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    # Determine client IP (respect X-Forwarded-For behind a reverse proxy)
    forwarded = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded.split(",")[0].strip() or request.client.host if request.client else "unknown"

    from app.services.rate_limiter import rate_limiter

    allowed, count = await rate_limiter.check(
        key=f"ip:{client_ip}",
        max_requests=100,   # 100 requests per…
        window_seconds=60,  # …60 seconds
    )

    if not allowed:
        trace_id = _get_trace_id(request)
        logger.warning(
            "Rate limit exceeded for %s (%d req/min)",
            client_ip,
            count,
            extra={"trace_id": trace_id},
        )
        return _make_error_response(
            status_code=429,
            code="RATE_LIMITED",
            message="Too many requests. Please slow down.",
            trace_id=trace_id,
            hint="Retry after 60 seconds",
        )

    # Let the request through
    response = await call_next(request)
    # Attach rate-limit info headers (best-effort — response may already
    # have its own headers).
    response.headers["X-RateLimit-Limit"] = "100"
    response.headers["X-RateLimit-Remaining"] = str(max(0, 100 - count))
    return response


# -- Routers (all mounted under /api/v1) --
app.include_router(auth.router, prefix="/api/v1")
app.include_router(drawings.router, prefix="/api/v1")
app.include_router(quantities.router, prefix="/api/v1")
app.include_router(materials.router, prefix="/api/v1")
app.include_router(costs.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(ai_features.router, prefix="/api/v1")
app.include_router(exports.router, prefix="/api/v1")
app.include_router(live.router, prefix="/api/v1")
app.include_router(doc_gen.router, prefix="/api/v1")
app.include_router(proposals.router, prefix="/api/v1")
# Celery monitoring (mounted under /api/v1 too)
app.include_router(celery_monitor_router, prefix="/api/v1")

# -- Root-level routers (no auth, no prefix) --
app.include_router(health_router)
app.include_router(metrics_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
