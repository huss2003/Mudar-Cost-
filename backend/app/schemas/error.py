"""Structured error response schemas.

Every API error response follows the same envelope::

    {
        "data": null,
        "error": {
            "trace_id": "uuid-string",
            "code": "ERROR_CODE",
            "message": "Human-readable description",
            "hint": "Optional guidance for the caller"
        }
    }

Success responses remain free-form (the envelope is for errors only).
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """A single error payload with traceability metadata."""

    trace_id: str
    code: str
    message: str
    hint: Optional[str] = None


class ErrorResponse(BaseModel):
    """Top-level error envelope returned on every failure."""

    data: Optional[Any] = None
    error: Optional[ErrorDetail] = None
