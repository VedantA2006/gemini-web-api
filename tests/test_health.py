"""Tests for service health endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    """Verify /health returns 200 with standard health status structure."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "browser_connected" in data
    assert "authenticated" in data
    assert "version" in data
    assert isinstance(data["browser_connected"], bool)
    assert isinstance(data["authenticated"], bool)
