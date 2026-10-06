"""Smoke tests for the FastAPI application."""

import httpx
import pytest

from backend.config import Settings
from backend.main import create_app


def test_application_starts() -> None:
    app = create_app(Settings(APP_ENV="test"))

    assert app.title == "cardiosmart-backend"
    assert app.state.settings.app_env == "test"


@pytest.mark.asyncio
async def test_health_endpoint_returns_service_status() -> None:
    app = create_app(Settings(APP_ENV="test"))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "cardiosmart-backend",
    }
