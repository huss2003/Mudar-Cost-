from fastapi import APIRouter

router = APIRouter(prefix="/costs", tags=["costs"])


@router.get("")
async def list_cost_estimates():
    """Stub: list cost estimates."""
    return {"message": "costs endpoint stub", "estimates": []}


@router.get("/{estimate_id}")
async def get_cost_estimate(estimate_id: str):
    """Stub: get a single cost estimate by ID."""
    return {"message": "costs endpoint stub", "estimate_id": estimate_id}
