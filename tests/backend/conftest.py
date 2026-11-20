
"""PostgreSQL integration-test fixtures for the backend."""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture(scope="session")
def test_database_engine() -> Iterator[Engine]:
    """Create an engine connected exclusively to a test database."""

    database_url = os.getenv("TEST_DATABASE_URL")

    if not database_url:
        if os.getenv("CI", "").lower() == "true":
            pytest.fail("TEST_DATABASE_URL must be configured in CI.")

        pytest.skip(
            "TEST_DATABASE_URL is not configured. "
            "Set it to a dedicated PostgreSQL test database to run integration tests."
        )

    database_name = make_url(database_url).database or ""

    if not (
        database_name.startswith("test")
        or database_name.endswith("_test")
    ):
        pytest.fail(
            "TEST_DATABASE_URL must point to a dedicated test database. "
            f"Refusing to use database '{database_name}'."
        )

    engine = create_engine(database_url, pool_pre_ping=True)

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_connection(test_database_engine: Engine) -> Iterator[Connection]:
    """Wrap each test in an outer transaction that is always rolled back."""

    connection = test_database_engine.connect()
    transaction = connection.begin()

    try:
        yield connection
    finally:
        if transaction.is_active:
            transaction.rollback()

        connection.close()


@pytest.fixture
def db_session_factory(
    db_connection: Connection,
) -> sessionmaker[Session]:
    """Create sessions that use savepoints inside the test transaction."""

    return sessionmaker(
        bind=db_connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest.fixture
def db_session(db_session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Provide a session for a test."""

    session = db_session_factory()

    try:
        yield session
    finally:
        session.close()
