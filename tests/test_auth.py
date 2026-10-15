"""Tests for API Key authentication and security."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import is_token_valid
from app.config import settings
from app.main import app


def test_constant_time_comparison(monkeypatch):
    """Test timing-safe token verification logic."""
    monkeypatch.setattr(settings, "API_KEY", "secret-test-key-12345")
    assert is_token_valid("secret-test-key-12345") is True
    assert is_token_valid("wrong-key") is False
    assert is_token_valid("") is False
    assert is_token_valid(None) is False


def test_allow_unauthenticated_when_key_unset(monkeypatch):
    """When API_KEY is empty/unset, local requests pass."""
    monkeypatch.setattr(settings, "API_KEY", None)
    assert is_token_valid(None) is True
    assert is_token_valid("any-key") is True


@pytest.mark.asyncio
async def test_auth_rejection_missing_header(monkeypatch):
    """Requests without Authorization header receive 401 when API_KEY is set."""
    monkeypatch.setattr(settings, "API_KEY", "super-secret-key")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/models")

    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["type"] == "authentication_error"
    assert data["error"]["code"] == "invalid_api_key"


@pytest.mark.asyncio
async def test_auth_rejection_invalid_token(monkeypatch):
    """Requests with wrong Bearer token receive 401."""
    monkeypatch.setattr(settings, "API_KEY", "super-secret-key")
    transport = ASGITransport(app=app)
    headers = {"Authorization": "Bearer wrong-token-value"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/models", headers=headers)

    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "invalid_api_key"


@pytest.mark.asyncio
async def test_auth_success_valid_token(monkeypatch):
    """Requests with correct Bearer token succeed."""
    monkeypatch.setattr(settings, "API_KEY", "super-secret-key")
    transport = ASGITransport(app=app)
    headers = {"Authorization": "Bearer super-secret-key"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/models", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert len(data["data"]) > 0
