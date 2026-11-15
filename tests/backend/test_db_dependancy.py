
"""FastAPI tests for database dependency behavior."""

from typing import Annotated
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import Depends
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.config import Settings
from backend.main import create_app


@pytest.mark.asyncio
async def test_successful_request_commits_and_closes_session() -> None:
    app = create_app(Settings(APP_ENV="test"))

    session = MagicMock(spec=Session)
    session_factory = MagicMock(return_value=session)
    app.state.session_factory = session_factory

    def test_endpoint(
        db: Annotated[Session, Depends(get_db, scope="function")],
    ) -> dict[str, str]:
        return {"status": "success"}

    app.add_api_route(
        "/test-write",
        test_endpoint,
        methods=["POST"],
    )

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.post("/test-write")

    assert response.status_code == 200
    assert response.json() == {"status": "success"}

    session_factory.assert_called_once_with()
    session.commit.assert_called_once()
    session.rollback.assert_not_called()
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_commit_failure_prevents_successful_response() -> None:
    app = create_app(Settings(APP_ENV="test"))

    session = MagicMock(spec=Session)
    session.commit.side_effect = RuntimeError("Database commit failed")

    session_factory = MagicMock(return_value=session)
    app.state.session_factory = session_factory

    def test_endpoint(
        db: Annotated[Session, Depends(get_db, scope="function")],
    ) -> dict[str, str]:
        return {"status": "success"}

    app.add_api_route(
        "/test-write",
        test_endpoint,
        methods=["POST"],
    )

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        with pytest.raises(RuntimeError, match="Database commit failed"):
            await client.post("/test-write")

    session_factory.assert_called_once_with()
    session.commit.assert_called_once()
    session.rollback.assert_called_once()
    session.close.assert_called_once()
