"""Smoke tests — verify the app starts and key endpoints respond."""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_health(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"


@pytest.mark.asyncio
async def test_docs_disabled_in_production(app):
    """Docs endpoint should be 404 when APP_DEBUG is false (default in tests)."""
    import os
    if os.getenv("APP_DEBUG", "false").lower() == "true":
        pytest.skip("docs enabled in debug mode")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/docs")
    assert resp.status_code == 404
