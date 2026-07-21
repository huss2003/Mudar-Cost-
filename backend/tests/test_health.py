"""Async health-check test for the FastAPI application."""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Provide an async test client over ASGI (no network needed)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    """GET /health returns 200 with status ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"status": "ok", "version": "0.1.0"}
