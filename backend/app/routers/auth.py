"""No-op authentication stub — always returns a dummy user."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])


class UserInfo(BaseModel):
    sub: str
    email: str
    name: str
    roles: list[str]


async def get_current_user() -> UserInfo:
    """No-op dependency: returns a fake admin user without checking any headers."""
    return UserInfo(
        sub="anonymous",
        email="user@example.com",
        name="Demo User",
        roles=["admin"],
    )


async def require_role(role: str):
    """No-op dependency factory: always allows access."""

    async def _check(
        current_user: UserInfo = Depends(get_current_user),
    ) -> UserInfo:
        return current_user

    return _check


@router.get("/me", response_model=UserInfo)
async def read_current_user(
    current_user: UserInfo = Depends(get_current_user),
):
    """Return the fake authenticated user's profile."""
    return current_user
