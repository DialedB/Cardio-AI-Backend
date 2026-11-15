
"""Tests for database session lifecycle and transaction handling."""
from unittest.mock import MagicMock

import pytest
from backend.api.deps import get_db
from fastapi import FastAPI

from backend.db.session import session_scope


def test_session_scope_commits_and_closes() -> None:
    factory = MagicMock()
    session = factory.return_value

    generator = session_scope(factory)
    yielded_session = next(generator)

    assert yielded_session is session

    with pytest.raises(StopIteration):
        next(generator)

    factory.assert_called_once_with()
    session.commit.assert_called_once()
    session.rollback.assert_not_called()
    session.close.assert_called_once()


def test_session_scope_rolls_back_and_closes_on_exception() -> None:
    factory = MagicMock()
    session = factory.return_value

    generator = session_scope(factory)
    yielded_session = next(generator)

    assert yielded_session is session

    with pytest.raises(RuntimeError, match="Database operation failed"):
        generator.throw(RuntimeError("Database operation failed"))

    factory.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()
    session.close.assert_called_once()


def test_session_scope_rolls_back_if_commit_fails() -> None:
    factory = MagicMock()
    session = factory.return_value
    session.commit.side_effect = RuntimeError("Commit failed")

    generator = session_scope(factory)
    next(generator)

    with pytest.raises(RuntimeError, match="Commit failed"):
        next(generator)

    factory.assert_called_once_with()
    session.commit.assert_called_once()
    session.rollback.assert_called_once()
    session.close.assert_called_once()


def test_get_db_uses_application_session_factory() -> None:
    app = FastAPI()
    factory = MagicMock()
    app.state.session_factory = factory

    request = MagicMock()
    request.app = app

    generator = get_db(request)
    yielded_session = next(generator)

    assert yielded_session is factory.return_value

    with pytest.raises(StopIteration):
        next(generator)

    factory.assert_called_once_with()
    factory.return_value.commit.assert_called_once()
    factory.return_value.rollback.assert_not_called()
    factory.return_value.close.assert_called_once()


def test_get_db_rolls_back_and_closes_on_exception() -> None:
    app = FastAPI()
    factory = MagicMock()
    app.state.session_factory = factory

    request = MagicMock()
    request.app = app

    generator = get_db(request)
    yielded_session = next(generator)

    assert yielded_session is factory.return_value

    with pytest.raises(RuntimeError, match="Database operation failed"):
        generator.throw(RuntimeError("Database operation failed"))

    factory.assert_called_once_with()
    factory.return_value.commit.assert_not_called()
    factory.return_value.rollback.assert_called_once()
    factory.return_value.close.assert_called_once()
