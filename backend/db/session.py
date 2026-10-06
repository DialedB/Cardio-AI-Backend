"""SQLAlchemy engine and session construction."""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    """Create an engine without connecting until the first database operation."""

    return create_engine(settings.database_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the application's database session factory."""

    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a session and guarantee it is closed by the caller's dependency system."""

    session = factory()
    try:
        yield session
    finally:
        session.close()
