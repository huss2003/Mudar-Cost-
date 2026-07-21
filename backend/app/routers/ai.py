from fastapi import APIRouter

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/capabilities")
async def ai_capabilities():
    """Stub: list AI-powered capabilities available."""
    return {"message": "ai endpoint stub", "capabilities": ["mimo", "deepseek"]}


@router.post("/extract")
async def ai_extract():
    """Stub: trigger AI extraction from a drawing."""
    return {"message": "ai endpoint stub", "status": "extraction queued"}


@router.post("/suggest")
async def ai_suggest():
    """Stub: get AI suggestions for materials / costs."""
    return {"message": "ai endpoint stub", "suggestions": []}
