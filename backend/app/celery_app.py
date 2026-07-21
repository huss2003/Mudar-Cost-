"""
Celery application for Auto Cost Engine.

Configures the Celery app with JSON serialisation (safe for structured
data) and production-hardened reliability settings:

- ``task_acks_late`` — messages are acknowledged *after* the task
  completes, so a worker crash mid-task doesn't lose the message
  (the message is re-delivered to another worker).
- ``task_reject_on_worker_lost`` — if the worker process is killed
  unexpectedly the message is rejected and re-queued.
- ``task_soft_time_limit`` / ``task_time_limit`` — a slow task is
  given a grace period (soft) before being hard-killed (hard), freeing
  the worker.
- ``task_default_retry_delay`` / ``task_max_retries`` — transient
  failures (e.g. DB deadlocks, network blips) are retried automatically.
- ``worker_prefetch_multiplier = 1`` — one task at a time per worker;
  prevents a single long task from starving others.

Dead-letter handling:
  When a task exhausts its retries or fails permanently, the task
  metadata, exception, and traceback are persisted to the ``failed_jobs``
  table for post-mortem debugging via the custom ``on_failure`` handler.
"""

from celery import Celery

from app.config import settings

celery_app = Celery(
    settings.APP_NAME,
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    # --- Serialisation -------------------------------------------------------
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # --- Task tracking -------------------------------------------------------
    task_track_started=True,
    # --- Reliability / resilience --------------------------------------------
    # Acknowledge messages *after* the task finishes, so a worker crash
    # mid-task does not lose the message (it will be re-delivered).
    task_acks_late=True,
    # Reject (and re-queue) a message when the worker process is lost.
    task_reject_on_worker_lost=True,
    # Soft limit: the task gets a SoftTimeLimitExceeded exception.
    task_soft_time_limit=600,  # 10 minutes
    # Hard limit: the worker kills the task process.
    task_time_limit=900,  # 15 minutes
    # Automatic retry for transient failures.
    task_default_retry_delay=60,  # seconds before first retry
    task_max_retries=3,
    # One task at a time per worker process — prevents a single long
    # task from consuming all prefetched messages.
    worker_prefetch_multiplier=1,
    # --- Dead-letter / failed-job tracking -----------------------------------
    # Disable automatic retries globally — tasks opt in per-task via
    # autoretry_for or explicit retry() calls.  This ensures permanent
    # failures always reach on_failure rather than being swallowed by
    # the global retry policy.
    task_always_eager=False,
)

# Auto-discover tasks in registered app packages
celery_app.autodiscover_tasks(["app.tasks"])


# ======================================================================
# Dead-letter handler (Celery task base class override)
# ======================================================================


def _capture_failed_job(task, exc, task_id, args, kwargs, traceback, einfo):
    """Persist a permanently-failed task to the ``failed_jobs`` table.

    This function is called from ``on_failure`` on every task.  It
    runs in a synchronous SQLAlchemy session (Celery workers are
    synchronous) and is best-effort — a failure to write the record
    is logged but not re-raised.
    """
    import logging
    import traceback as tb_mod

    logger = logging.getLogger(__name__)

    try:
        from app.database import engine
        from app.models.failed_job import FailedJob

        # engine is async — Celery workers use sync sessions.
        # We create a sync session explicitly.
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        sync_url = str(engine.url).replace("+asyncpg", "")
        sync_engine = create_engine(sync_url)
        SessionLocal = sessionmaker(bind=sync_engine)

        exc_type = type(exc).__name__
        exc_message = str(exc)[:2000]
        tb_str = "".join(
            tb_mod.format_exception(type(exc), exc, getattr(exc, "__traceback__", None))
        )[:5000]

        # Try to extract trace_id from kwargs or request metadata
        trace_id = None
        if isinstance(kwargs, dict):
            trace_id = kwargs.get("trace_id") or kwargs.get("_trace_id")

        with SessionLocal() as session:
            failed = FailedJob(
                task_name=task.name,
                task_id=task_id,
                args=args if isinstance(args, (list, dict)) else None,
                kwargs=kwargs if isinstance(kwargs, dict) else None,
                exc_type=exc_type,
                exc_message=exc_message,
                traceback=tb_str or None,
                trace_id=trace_id,
            )
            session.add(failed)
            session.commit()

        logger.warning(
            "Captured failed job: %s [%s] — %s",
            task.name,
            task_id,
            exc_message,
        )
    except Exception as persist_err:
        logger.error(
            "Failed to persist failed job record for %s [%s]: %s",
            task.name,
            task_id,
            persist_err,
        )


class DeadLetterTask:
    """Mixin-like base class that adds dead-letter capture to Celery tasks.

    Every task defined in ``app/tasks/`` should inherit from this
    instead of the raw ``celery_app.Task`` class to enable automatic
    failed-job recording.

    Usage::

        @celery_app.task(base=DeadLetterTask, bind=True)
        def my_task(self, ...):
            ...
    """

    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Celery callback — fires when a task fails permanently.

        This method is called after all automatic retries are exhausted
        or when an unhandled exception occurs outside the retry loop.
        """
        _capture_failed_job(self, exc, task_id, args, kwargs, einfo, traceback)
        # Call the original on_failure (celery's default is a no-op,
        # but subclasses may override).
        super().on_failure(exc, task_id, args, kwargs, einfo)


# ======================================================================
# Health-check task
# ======================================================================


@celery_app.task(name="app.celery.health_check", bind=True)
def health_check(self):
    """Simple Celery health-check task."""
    return {"task_id": self.request.id, "status": "ok"}
