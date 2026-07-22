"""Vercel Python serverless handler for Auto Cost Engine."""
import sys, os, logging

# Add backend to path
backend_dir = os.path.join(os.path.dirname(__file__), '..', 'backend')
sys.path.insert(0, backend_dir)

# Set Vercel-appropriate defaults
os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("SECRET_KEY", "vercel-secret-key-32-chars-minimum-ok")
os.environ.setdefault("CORS_ORIGINS", '["*"]')
os.environ.setdefault("MINIO_ENDPOINT", "")
os.environ.setdefault("MINIO_ACCESS_KEY", "")
os.environ.setdefault("MINIO_SECRET_KEY", "")

from mangum import Mangum

try:
    from app.main import app
    handler = Mangum(app, lifespan="off")
except Exception as e:
    # Fallback: minimal app if imports fail
    logging.error(f"Failed to import full app: {e}")
    from fastapi import FastAPI
    app = FastAPI(title="Auto Cost Engine")
    
    @app.get("/api/healthz")
    async def healthz():
        return {"status": "alive", "mode": "fallback"}
    
    from mangum import Mangum
    handler = Mangum(app, lifespan="off")
