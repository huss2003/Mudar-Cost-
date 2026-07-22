"""Vercel serverless entry point for Auto Cost Engine backend."""
import sys
import os

# Add the backend directory to the path
backend_dir = os.path.join(os.path.dirname(__file__), '..', 'backend')
sys.path.insert(0, os.path.abspath(backend_dir))

# Set default env vars for Vercel if not already set
os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL", ""))
os.environ.setdefault("CORS_ORIGINS", os.environ.get("CORS_ORIGINS", '["*"]'))
os.environ.setdefault("SECRET_KEY", os.environ.get("SECRET_KEY", "vercel-secret-key-min-32-chars-long!!"))

from app.main import app

# Vercel Python ASGI handler
handler = app
