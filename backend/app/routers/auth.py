"""OIDC / JWT authentication router with real Keycloak verification.

Provides:
  - POST /auth/token-exchange — exchange auth code for tokens via Keycloak
  - GET  /auth/me           — return the authenticated user's profile
  - get_current_user        — FastAPI dependency (JWT verification via JWKS)
  - require_role            — dependency factory for role-based access control
"""

import logging
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError
from jose.jwk import construct
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UserInfo(BaseModel):
    sub: str
    email: str
    name: str
    roles: list[str]


class TokenExchangeRequest(BaseModel):
    code: str
    redirect_uri: str


class TokenExchangeResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str = ""


# ---------------------------------------------------------------------------
# JWKS cache
# ---------------------------------------------------------------------------

_jwks_data: Optional[dict[str, Any]] = None
_jwks_fetched_at: float = 0
_JWKS_CACHE_TTL: float = 3600  # 1 hour

_JWKS_URL = (
    f"{settings.KEYCLOAK_URL}/realms/"
    f"{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs"
)


async def _fetch_jwks() -> dict[str, Any]:
    """Fetch the JWKS key set from Keycloak, with caching."""
    global _jwks_data, _jwks_fetched_at

    now = time.monotonic()
    if _jwks_data is not None and (now - _jwks_fetched_at) < _JWKS_CACHE_TTL:
        return _jwks_data

    async with httpx.AsyncClient() as client:
        resp = await client.get(_JWKS_URL, timeout=10)
        resp.raise_for_status()
        _jwks_data = resp.json()
        _jwks_fetched_at = now
        logger.info("Fetched JWKS (%d keys)", len(_jwks_data.get("keys", [])))
        return _jwks_data


def _find_signing_key(jwks: dict[str, Any], kid: str) -> Optional[dict[str, Any]]:
    """Find the JWK whose ``kid`` matches the token's ``kid`` header."""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


def _build_rsa_key(jwk_dict: dict[str, Any]) -> Any:
    """Build a python-jose key object from a JWK dictionary.

    Handles both ``n``/``e`` (RSA public key) and ``x5c`` (X.509 cert)
    representations.
    """
    if "x5c" in jwk_dict and jwk_dict["x5c"]:
        # Build from the first X.509 certificate
        cert_der = jwk_dict["x5c"][0]
        return construct(cert_der, algorithm="RS256")
    # Build from modulus + exponent
    return construct(jwk_dict, algorithm="RS256")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OIDC_CONFIG_URL = (
    f"{settings.KEYCLOAK_URL}/realms/"
    f"{settings.KEYCLOAK_REALM}/.well-known/openid-configuration"
)

_issuer: Optional[str] = None


async def _get_issuer() -> str:
    """Fetch the expected issuer from the OIDC discovery document."""
    global _issuer
    if _issuer is not None:
        return _issuer
    async with httpx.AsyncClient() as client:
        resp = await client.get(_OIDC_CONFIG_URL, timeout=10)
        resp.raise_for_status()
        _issuer = resp.json()["issuer"]
        return _issuer


def _userinfo_from_claims(claims: dict) -> UserInfo:
    """Build a UserInfo from verified JWT claims."""
    realm_access = claims.get("realm_access", {})
    roles: list[str] = realm_access.get("roles", [])
    return UserInfo(
        sub=claims.get("sub", ""),
        email=claims.get("email", ""),
        name=claims.get("name")
        or claims.get("preferred_username", "")
        or claims.get("email", ""),
        roles=roles,
    )


async def _upsert_user(db: AsyncSession, info: UserInfo) -> User:
    """Look up user by keycloak ``sub``; create if not found."""
    result = await db.execute(select(User).where(User.sub == info.sub))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            sub=info.sub,
            email=info.email or None,
            display_name=info.name or None,
            role=info.roles[0] if info.roles else "estimator",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        logger.info("Created new user from Keycloak: sub=%s", info.sub)
    else:
        # Update fields that may have changed in Keycloak
        if info.email:
            user.email = info.email
        if info.name:
            user.display_name = info.name
        if info.roles:
            user.role = info.roles[0]
        logger.debug("Updated user from Keycloak: sub=%s", info.sub)

    return user


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserInfo:
    """FastAPI dependency: extract and verify the Bearer JWT from the request.

    Verifies signature, expiry, issuer, and audience against Keycloak's JWKS.
    Looks up or creates the corresponding ``User`` row in the database.
    Returns a ``UserInfo`` pydantic model.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header[7:]  # strip "Bearer "
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is empty",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # 1. Get the kid from the JWT header (without verification)
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing 'kid' header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 2. Fetch JWKS and find the matching key
        jwks = await _fetch_jwks()
        jwk_data = _find_signing_key(jwks, kid)
        if jwk_data is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No matching signing key found in JWKS",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 3. Build the signing key and verify the JWT
        signing_key = _build_rsa_key(jwk_data)
        issuer = await _get_issuer()

        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.KEYCLOAK_CLIENT_ID,
            issuer=issuer,
            options={
                "verify_signature": True,
                "verify_aud": True,
                "verify_iss": True,
                "verify_exp": True,
            },
        )

        info = _userinfo_from_claims(claims)
        await _upsert_user(db, info)
        return info

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_role(role: str):
    """Dependency factory: require a specific Keycloak realm role.

    Usage::

        @router.get("/admin-only")
        async def admin_endpoint(
            _: UserInfo = Depends(require_role("admin")),
        ):
            ...
    """

    async def _check(current_user: UserInfo = Depends(get_current_user)) -> UserInfo:
        if role not in current_user.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required role: {role}",
            )
        return current_user

    return _check


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/me", response_model=UserInfo)
async def read_current_user(
    current_user: UserInfo = Depends(get_current_user),
):
    """Return the authenticated user's profile."""
    return current_user


@router.post("/token-exchange", response_model=TokenExchangeResponse)
async def token_exchange(
    body: TokenExchangeRequest,
):
    """Exchange an OIDC authorization code for Keycloak tokens.

    This is used by the frontend after the browser redirects back from
    the Keycloak login page with a ``?code=...`` query parameter.
    """
    token_url = (
        f"{settings.KEYCLOAK_URL}/realms/"
        f"{settings.KEYCLOAK_REALM}/protocol/openid-connect/token"
    )

    data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": body.code,
        "redirect_uri": body.redirect_uri,
        "client_id": settings.KEYCLOAK_CLIENT_ID,
    }
    if settings.KEYCLOAK_CLIENT_SECRET:
        data["client_secret"] = settings.KEYCLOAK_CLIENT_SECRET

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(token_url, data=data, timeout=30)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Keycloak token exchange failed: %s %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token exchange with Keycloak failed",
            )

    token_data = resp.json()
    return TokenExchangeResponse(
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token", ""),
        expires_in=token_data.get("expires_in", 300),
    )


@router.post("/refresh", response_model=TokenExchangeResponse)
async def refresh_token(
    body: TokenRefreshRequest,
):
    """Refresh an access token using a refresh token."""
    token_url = (
        f"{settings.KEYCLOAK_URL}/realms/"
        f"{settings.KEYCLOAK_REALM}/protocol/openid-connect/token"
    )

    data: dict[str, str] = {
        "grant_type": "refresh_token",
        "refresh_token": body.refresh_token,
        "client_id": settings.KEYCLOAK_CLIENT_ID,
    }
    if settings.KEYCLOAK_CLIENT_SECRET:
        data["client_secret"] = settings.KEYCLOAK_CLIENT_SECRET

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(token_url, data=data, timeout=30)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Keycloak token refresh failed: %s %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token refresh with Keycloak failed",
            )

    token_data = resp.json()
    return TokenExchangeResponse(
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token", body.refresh_token),
        expires_in=token_data.get("expires_in", 300),
    )


@router.post("/logout")
async def logout(
    request: Request,
    body: LogoutRequest = None,
):
    """Log out from Keycloak (optional, best-effort).

    Reads the Authorization header for the access token and optionally
    accepts a ``refresh_token`` in the request body to invalidate the
    Keycloak session.  Returns 200 even if Keycloak is unreachable —
    the frontend clears local tokens regardless.
    """
    auth_header = request.headers.get("Authorization", "")
    access_token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

    logout_url = (
        f"{settings.KEYCLOAK_URL}/realms/"
        f"{settings.KEYCLOAK_REALM}/protocol/openid-connect/logout"
    )

    data: dict[str, str] = {
        "client_id": settings.KEYCLOAK_CLIENT_ID,
    }

    if settings.KEYCLOAK_CLIENT_SECRET:
        data["client_secret"] = settings.KEYCLOAK_CLIENT_SECRET

    # Keycloak prefers a refresh_token or id_token_hint to end the session
    if body and body.refresh_token:
        data["refresh_token"] = body.refresh_token
    elif access_token:
        data["id_token_hint"] = access_token

    async with httpx.AsyncClient() as client:
        try:
            await client.post(logout_url, data=data, timeout=10)
        except httpx.HTTPError:
            logger.warning("Keycloak logout request failed (best-effort)")

    return {"message": "logged out"}
