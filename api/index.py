"""Vercel Python serverless handler for Auto Cost Engine API."""
import sys, os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# Set defaults for Vercel
os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("SECRET_KEY", "vercel-secret-key-32-chars-minimum-ok")
os.environ.setdefault("CORS_ORIGINS", '["*"]')
os.environ.setdefault("MINIO_ENDPOINT", "")
os.environ.setdefault("MINIO_ACCESS_KEY", "")
os.environ.setdefault("MINIO_SECRET_KEY", "")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create a minimal app that doesn't import all the heavy modules
app = FastAPI(title="Auto Cost Engine API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/healthz")
async def healthz():
    return {"status": "alive"}

@app.get("/api/v1/projects")
async def list_projects():
    return {"projects": [], "message": "Supabase-connected mode"}

from mangum import Mangum
handler = Mangum(app, lifespan="off")
