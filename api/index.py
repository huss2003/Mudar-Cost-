"""Vercel Python serverless handler for Auto Cost Engine API."""
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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# Create a minimal API that routes to Supabase Edge Functions
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
    return {"status": "alive", "version": "1.0.0"}

@app.get("/api/v1/{path:path}")
async def proxy_api(path: str, request: Request):
    """Proxy API requests to Supabase Edge Functions"""
    import httpx
    
    supabase_url = os.environ.get("SUPABASE_URL", "https://pecnshwflkwpnwiskgmg.supabase.co")
    supabase_key = os.environ.get("SUPABASE_ANON_KEY", "sb_publishable_GMkHBBICoUbKeg5W1UGtFg_Y-_xU0yb")
    
    target_url = f"{supabase_url}/functions/v1/api/{path}"
    method = request.method
    body = await request.body() if method in ("POST", "PUT", "PATCH") else None
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method, target_url,
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/json",
            },
            content=body,
        )
    
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=resp.status_code,
        content=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"data": resp.text},
    )

# Mangum adapter for Vercel
from mangum import Mangum
handler = Mangum(app, lifespan="off")
