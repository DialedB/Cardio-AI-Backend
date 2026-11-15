
"""Smoke and lifespan tests for the FastAPI application."""

from unittest.mock import MagicMock

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

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "cardiosmart-backend",
    }


@pytest.mark.asyncio
async def test_lifespan_creates_and_disposes_engine(monkeypatch) -> None:
    engine = MagicMock()
    session_factory = MagicMock()

    create_engine = MagicMock(return_value=engine)
    create_factory = MagicMock(return_value=session_factory)

    monkeypatch.setattr(
        "backend.main.create_database_engine",
        create_engine,
    )
    monkeypatch.setattr(
        "backend.main.create_session_factory",
        create_factory,
    )

    app = create_app(Settings(APP_ENV="test"))

    # Creating the application must not create an engine.
    create_engine.assert_not_called()

    async with app.router.lifespan_context(app):
        create_engine.assert_called_once_with(app.state.settings)
        create_factory.assert_called_once_with(engine)

        assert app.state.engine is engine
        assert app.state.session_factory is session_factory

        engine.dispose.assert_not_called()

    engine.dispose.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_disposes_engine_if_startup_fails(monkeypatch) -> None:
    engine = MagicMock()

    monkeypatch.setattr(
        "backend.main.create_database_engine",
        lambda settings: engine,
    )
    monkeypatch.setattr(
        "backend.main.create_session_factory",
        MagicMock(side_effect=RuntimeError("Factory creation failed")),
    )

    app = create_app(Settings(APP_ENV="test"))

    with pytest.raises(RuntimeError, match="Factory creation failed"):
        async with app.router.lifespan_context(app):
            pass

    engine.dispose.assert_called_once()
