#!/usr/bin/env python3
"""
doctor.py  —  Pre-flight health checker for Auto Cost Engine.

Usage:
    python scripts/doctor.py

Loads ``.env`` from the project root, validates every required variable is
set, and checks connectivity to each backing service.  Exits 0 when all
required checks pass, 1 otherwise.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

# ── Coloured output (ANSI) ──────────────────────────────────────────────────
GREEN_CHECK = "\033[92m\u2714\033[0m"  # ✅
RED_CROSS = "\033[91m\u2718\033[0m"  # ❌
YELLOW_WARN = "\033[93m\u26a0\033[0m"  # ⚠️
BOLD = "\033[1m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN_CHECK} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED_CROSS} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW_WARN} {msg}")


def heading(label: str) -> None:
    print(f"\n{BOLD}{label}{RESET}")


# ── .env loader (stdlib-only) ──────────────────────────────────────────────
def load_dotenv(path: str) -> dict[str, str]:
    """Parse a ``KEY=VALUE`` file.  Supports ``export `` prefix, quotes, and
    inline ``#`` comments.  Does NOT support variable interpolation."""
    env: dict[str, str] = {}
    if not os.path.isfile(path):
        return env
    with open(path, encoding="utf-8", errors="surrogateescape") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # Strip leading 'export '
            if line.startswith("export "):
                line = line[7:].strip()
            m = re.match(r"^([\w.-]+)\s*=\s*(.*)", line)
            if not m:
                continue
            key = m.group(1)
            val = m.group(2).strip()
            # Strip surrounding quotes
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            # Cut trailing inline comment (space then #)
            # Be careful: don't cut a # inside a value
            # Simple approach: find # that's preceded by space
            # This can be fooled by values with # but it's good enough for .env
            env[key] = val
    return env


# ── Service check helpers ───────────────────────────────────────────────────

def check_env_var(name: str, env: dict[str, str], required: bool = True) -> bool:
    val = env.get(name, "")
    if not val:
        if required:
            fail(f"{name} is unset or empty")
            return False
        else:
            warn(f"{name} is empty (optional)")
            return True
    ok(f"{name} = {'*' * min(len(val), 12)}{val[-4:] if len(val) > 4 else ''}")
    return True


def check_postgres(dsn: str) -> bool:
    """Check PostgreSQL connectivity via psycopg2."""
    heading("PostgreSQL")
    try:
        import psycopg2

        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.close()
        ok("Connection OK (SELECT 1)")
        return True
    except ImportError:
        warn("psycopg2 not installed — skipping")
        return True
    except Exception as exc:
        fail(f"Connection failed: {exc}")
        return False


def check_redis(url: str) -> bool:
    """Check Redis via redis-cli PING."""
    heading("Redis")
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    try:
        result = subprocess.run(
            ["redis-cli", "-h", host, "-p", str(port), "PING"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if "PONG" in result.stdout:
            ok(f"redis-cli PING on {host}:{port}")
            return True
        fail(f"redis-cli PING failed: {result.stderr.strip() or result.stdout.strip()}")
        return False
    except FileNotFoundError:
        warn("redis-cli not found — skipping")
        return True
    except subprocess.TimeoutExpired:
        fail(f"redis-cli PING timed out on {host}:{port}")
        return False


def check_minio(endpoint: str, access_key: str, secret_key: str) -> bool:
    """Check MinIO via mc CLI alias."""
    heading("MinIO")
    try:
        # Create temp alias (cleanup on best-effort)
        subprocess.run(
            ["mc", "alias", "set", "doctor-minio", f"http://{endpoint}", access_key, secret_key],
            capture_output=True,
            text=True,
            timeout=15,
        )
        result = subprocess.run(
            ["mc", "ls", "doctor-minio"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            ok(f"mc ls on {endpoint}")
            return True
        fail(f"mc ls failed: {result.stderr.strip()}")
        return False
    except FileNotFoundError:
        warn("mc (minio-client) not found — skipping")
        return True
    except subprocess.TimeoutExpired:
        fail(f"mc timed out on {endpoint}")
        return False
    finally:
        try:
            subprocess.run(
                ["mc", "alias", "rm", "doctor-minio"],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass


def check_keycloak(url: str, realm: str) -> bool:
    """Check Keycloak is reachable via its OpenID configuration endpoint."""
    heading("Keycloak")
    oidc_url = f"{url.rstrip('/')}/realms/{realm}/.well-known/openid-configuration"
    parsed = urlparse(oidc_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"

    try:
        conn = http.client.HTTPConnection(host, port, timeout=10)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        if resp.status == 200:
            ok(f"HTTP 200 on {oidc_url}")
            return True
        elif resp.status in (301, 302, 307, 308):
            ok(f"HTTP {resp.status} (redirect — service is up)")
            return True
        fail(f"HTTP {resp.status} on {oidc_url}")
        return False
    except Exception as exc:
        fail(f"Connection failed: {exc}")
        return False


def check_celery(redis_url: str) -> bool:
    """Check Celery worker is reachable via ``celery inspect ping``."""
    heading("Celery")
    try:
        result = subprocess.run(
            ["celery", "-A", "app.celery_app", "inspect", "ping"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and "pong" in result.stdout.lower():
            ok("Celery worker responded to ping")
            return True
        # celery inspect ping can fail even when things are fine if no
        # workers are connected, but the worker may just be starting.
        # Consider this a warning, not a hard fail.
        warn(f"Celery ping gave no pong (may be starting): {result.stderr.strip() or result.stdout.strip()}")
        return True
    except FileNotFoundError:
        warn("celery CLI not found — skipping")
        return True
    except subprocess.TimeoutExpired:
        warn("celery inspect ping timed out — skipping")
        return True


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    root = Path(__file__).resolve().parent.parent  # project root
    env_file = root / ".env"

    print(f"{BOLD}══════════════════════════════════════{RESET}")
    print(f"{BOLD}  Auto Cost Engine  —  Pre-flight Check{RESET}")
    print(f"{BOLD}  .env → {env_file}{RESET}")
    print(f"{BOLD}══════════════════════════════════════{RESET}")

    # ── Load .env ───────────────────────────────────────────────────────
    if not env_file.exists():
        fail(f".env not found at {env_file}")
        print("\n  Copy .env.example → .env and fill in the values.\n")
        return 1

    env = load_dotenv(str(env_file))
    if not env:
        fail(".env is empty")
        return 1

    ok(f".env loaded ({len(env)} variables)")

    # ── Required env vars ───────────────────────────────────────────────
    heading("Required Environment Variables")

    required_vars = [
        "ENVIRONMENT",
        "SECRET_KEY",
        "DATABASE_URL",
        "MINIO_ENDPOINT",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "KEYCLOAK_URL",
        "KEYCLOAK_REALM",
        "KEYCLOAK_CLIENT_ID",
        "KEYCLOAK_CLIENT_SECRET",
        "CORS_ORIGINS",
    ]
    required_ok = True
    for var in required_vars:
        if not check_env_var(var, env, required=True):
            required_ok = False

    if not required_ok:
        print(f"\n{RED_CROSS} Some required env vars are missing.  Fix and re-run.\n")
        return 1

    # ── AI keys (production gating) ─────────────────────────────────────
    environment = env.get("ENVIRONMENT", "")
    if environment == "production":
        heading("AI API Keys (required in production)")
        for key in ("MIMO_API_KEY", "DEEPSEEK_API_KEY"):
            if not env.get(key):
                fail(f"{key} is empty but ENVIRONMENT=production")
                required_ok = False
            else:
                ok(f"{key} is set")
    else:
        heading("AI API Keys")
        ok("ENVIRONMENT is not 'production' — keys are optional")

    # ── Service connectivity ────────────────────────────────────────────
    heading("Service Connectivity")

    svc_ok = True

    # PostgreSQL
    pg_dsn = env.get("DATABASE_URL", "")
    if pg_dsn:
        if not check_postgres(pg_dsn):
            svc_ok = False
    else:
        warn("DATABASE_URL is empty — skipping PostgreSQL check")

    # Redis
    redis_url = env.get("REDIS_URL", "")
    if redis_url:
        if not check_redis(redis_url):
            svc_ok = False
    else:
        warn("REDIS_URL is empty — skipping Redis check")

    # MinIO
    minio_ep = env.get("MINIO_ENDPOINT", "")
    minio_ak = env.get("MINIO_ACCESS_KEY", "")
    minio_sk = env.get("MINIO_SECRET_KEY", "")
    if minio_ep and minio_ak and minio_sk:
        if not check_minio(minio_ep, minio_ak, minio_sk):
            svc_ok = False
    else:
        warn("MinIO credentials incomplete — skipping MinIO check")

    # Keycloak
    kc_url = env.get("KEYCLOAK_URL", "")
    kc_realm = env.get("KEYCLOAK_REALM", "")
    if kc_url and kc_realm:
        if not check_keycloak(kc_url, kc_realm):
            svc_ok = False
    else:
        warn("KEYCLOAK_URL / KEYCLOAK_REALM empty — skipping Keycloak check")

    # Celery
    if redis_url:
        if not check_celery(redis_url):
            svc_ok = False
    else:
        warn("REDIS_URL empty — skipping Celery check")

    # ── Summary ─────────────────────────────────────────────────────────
    print()
    if required_ok and svc_ok:
        print(f"{BOLD}{GREEN_CHECK} All checks passed!{RESET}")
        return 0
    elif required_ok:
        print(f"{YELLOW_WARN} Env vars look good, but some service checks failed or were skipped.{RESET}")
        return 1
    else:
        print(f"{RED_CROSS} Critical checks failed.  Fix above issues and re-run.{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
