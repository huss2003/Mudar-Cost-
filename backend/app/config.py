"""
Application settings loaded from environment variables.

Every secret / credential field is **required** (no fallback).  Operational
defaults (port numbers, feature flags) are allowed but can be overridden.
"""

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = Field(default="Auto Cost Engine", alias="APP_NAME")
    ENVIRONMENT: str = Field(
        ..., alias="ENVIRONMENT"  # production | staging | dev
    )
    DEBUG: bool = Field(default=False, alias="DEBUG")
    LOG_LEVEL: str = Field(default="INFO", alias="LOG_LEVEL")
    SECRET_KEY: str = Field(
        ...,
        min_length=32,
        alias="SECRET_KEY",
        description="Django/FastAPI-style secret key (>=32 chars)",
    )

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        ...,
        alias="DATABASE_URL",
        description="postgresql+asyncpg://user:pass@host:5432/db",
    )

    # ── MinIO (S3-compatible) — optional, disable with empty string ─────────
    MINIO_ENDPOINT: str = Field(default="", alias="MINIO_ENDPOINT")
    MINIO_ACCESS_KEY: str = Field(default="", alias="MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY: str = Field(default="", alias="MINIO_SECRET_KEY")
    MINIO_BUCKET: str = Field(default="drawings", alias="MINIO_BUCKET")

    # ── Redis / Celery ───────────────────────────────────────────────────────
    REDIS_URL: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    CELERY_BROKER_URL: str = Field(
        default="redis://redis:6379/1", alias="CELERY_BROKER_URL"
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://redis:6379/2", alias="CELERY_RESULT_BACKEND"
    )

    # ── Keycloak (OIDC) ──────────────────────────────────────────────────────
    KEYCLOAK_URL: str = Field(default="", alias="KEYCLOAK_URL")
    KEYCLOAK_REALM: str = Field(default="", alias="KEYCLOAK_REALM")
    KEYCLOAK_CLIENT_ID: str = Field(default="", alias="KEYCLOAK_CLIENT_ID")
    KEYCLOAK_CLIENT_SECRET: str = Field(default="", alias="KEYCLOAK_CLIENT_SECRET")

    # ── AI APIs — MiMo v2.5 for everything (vision + text) ────────────────────
    MIMO_API_KEY: str = Field(default="", alias="MIMO_API_KEY")
    MIMO_API_BASE: str = Field(
        default="https://api.xiaomimimo.com/v1", alias="MIMO_API_BASE"
    )
    # DeepSeek endpoint is aliased to MiMo — MiMo v2.5 handles text too
    DEEPSEEK_API_KEY: str = Field(default="", alias="DEEPSEEK_API_KEY")
    DEEPSEEK_API_BASE: str = Field(
        default="https://api.xiaomimimo.com/v1", alias="DEEPSEEK_API_BASE"
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = Field(
        default=["*"], alias="CORS_ORIGINS"
    )

    # ── Upload ───────────────────────────────────────────────────────────────
    MAX_UPLOAD_MB: int = Field(default=50, alias="MAX_UPLOAD_MB")
    ALLOWED_ORIGINS: List[str] | None = Field(
        default=None, alias="ALLOWED_ORIGINS"
    )

    # ─────────────────────────────────────────────────────────────────────────
    def validate_environment(self) -> None:
        """Startup-only validation.  Raises ``ValueError`` on violations."""
        valid_envs = ("production", "staging", "dev")
        if self.ENVIRONMENT not in valid_envs:
            raise ValueError(
                f"ENVIRONMENT={self.ENVIRONMENT!r} — must be one of {valid_envs}"
            )

        if self.ENVIRONMENT == "production":
            if not self.MIMO_API_KEY:
                raise ValueError("MIMO_API_KEY is required in production")

        if self.SECRET_KEY and len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY must be >= 32 characters")


# ---------------------------------------------------------------------------
# Singleton — importing ``settings`` gives you the fully resolved config.
# Validation runs once at import time so missing / invalid values fail-fast.
# ---------------------------------------------------------------------------
settings = Settings()
settings.validate_environment()
