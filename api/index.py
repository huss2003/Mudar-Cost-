from mangum import Mangum
import sys, os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# Set defaults for Vercel
os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("SECRET_KEY", "vercel-secret-key-32-chars-minimum-ok")
os.environ.setdefault("CORS_ORIGINS", '["*"]')

from app.main import app

# Mangum adapter for Vercel Python serverless
handler = Mangum(app, lifespan="off")
