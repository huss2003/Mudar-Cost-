"""Failed job model for Celery dead-letter capture.

When a Celery task exceeds its retry limit or fails permanently, the
task metadata, exception, and traceback are persisted here for
post-mortem debugging and alerting.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FailedJob(Base):
    """A permanently-failed Celery task, captured via dead-letter handler."""

    __tablename__ = "failed_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    args: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    kwargs: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    exc_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    exc_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<FailedJob id={self.id} task={self.task_name!r}"
            f" task_id={self.task_id!r}>"
        )
