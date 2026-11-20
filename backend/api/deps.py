
"""Shared FastAPI dependencies."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from backend.db.session import session_scope


def get_db(request: Request) -> Iterator[Session]:
    """Provide one database session per request."""

    factory: sessionmaker[Session] = request.app.state.session_factory

    yield from session_scope(factory)
