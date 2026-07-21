"""
Trace ID management — contextvar-based trace_id propagation.

Provides ``get_trace_id()`` / ``set_trace_id()`` for reading and writing
the current request's trace ID, which is automatically bound to structlog
context vars so every log line carries it.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

import structlog

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    """Return the current trace_id, or ``""`` if none is set."""
    return trace_id_var.get()


def set_trace_id(trace_id: str | None = None) -> str:
    """Set and return a trace_id.

    When *trace_id* is *None* a new UUID4 hex string is generated.
    The value is stored in a ``ContextVar`` and also bound to structlog
    context vars so all subsequent log calls in the same execution
    context carry it.
    """
    if not trace_id:
        trace_id = str(uuid.uuid4())
    trace_id_var.set(trace_id)
    structlog.contextvars.bind_contextvars(trace_id=trace_id)
    return trace_id
