import structlog
from contextlib import asynccontextmanager
from typing import AsyncIterator

from minio import Minio
from minio.error import S3Error

from app.config import settings

logger = structlog.get_logger(__name__)


def get_minio_client() -> Minio:
    """Return a synchronous MinIO client configured from settings."""
    return Minio(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,  # set to True when MINIO_ENDPOINT uses TLS
    )


async def create_bucket_if_not_exists() -> None:
    if not settings.MINIO_ENDPOINT:
        return
    """Ensure the configured MinIO bucket exists.

    Should be called during application startup.
    """
    client = get_minio_client()
    bucket = settings.MINIO_BUCKET
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            logger.info("Created MinIO bucket '%s'", bucket)
        else:
            logger.debug("MinIO bucket '%s' already exists", bucket)
    except S3Error as exc:
        logger.warning("Failed to verify / create MinIO bucket '%s': %s", bucket, exc)


@asynccontextmanager
async def minio_client_ctx() -> AsyncIterator[Minio]:
    """Async context manager that yields a MinIO client.

    Usage::

        async with minio_client_ctx() as mc:
            mc.put_object(...)
    """
    client = get_minio_client()
    try:
        yield client
    finally:
        # Minio client has no async close — no-op for cleanup
        pass
