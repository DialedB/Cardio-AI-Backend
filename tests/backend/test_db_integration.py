
"""PostgreSQL integration tests for database transactions."""

from collections.abc import Iterator

import pytest
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    insert,
    select,
)
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.db.session import session_scope


@pytest.fixture
def records_table(db_connection: Connection) -> Iterator[Table]:
    """Create a temporary test-only table inside the test transaction."""

    metadata = MetaData()

    table = Table(
        "kan136_session_records",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("value", String(100), nullable=False),
        UniqueConstraint("value"),
    )

    metadata.create_all(db_connection)

    yield table

    metadata.drop_all(db_connection)


def test_committed_data_is_visible_to_another_session(
    db_session_factory: sessionmaker[Session],
    records_table: Table,
) -> None:
    """A successful session commit makes its data visible to another session."""

    first_session = db_session_factory()

    try:
        first_session.execute(
            insert(records_table).values(value="committed record")
        )
        first_session.commit()
    finally:
        first_session.close()

    second_session = db_session_factory()

    try:
        result = second_session.execute(
            select(records_table.c.value)
        ).scalar_one()

        assert result == "committed record"
    finally:
        second_session.close()


def test_failed_operation_rolls_back_changes(
    db_session_factory: sessionmaker[Session],
    records_table: Table,
) -> None:
    """An exception during a session scope rolls back its changes."""

    generator = session_scope(db_session_factory)
    session = next(generator)

    session.execute(
        insert(records_table).values(value="should be rolled back")
    )

    with pytest.raises(RuntimeError, match="Simulated failure"):
        generator.throw(RuntimeError("Simulated failure"))

    verification_session = db_session_factory()

    try:
        result = verification_session.execute(
            select(records_table.c.value)
        ).all()

        assert result == []
    finally:
        verification_session.close()


def test_commit_failure_rolls_back_changes(
    db_session_factory: sessionmaker[Session],
    records_table: Table,
) -> None:
    """A failed commit rolls back the failed transaction."""

    session = db_session_factory()

    try:
        session.execute(
            insert(records_table).values(value="unique record")
        )
        session.commit()
    finally:
        session.close()

    failing_session = db_session_factory()

    try:
        failing_session.execute(
            insert(records_table).values(value="unique record")
        )

        with pytest.raises(IntegrityError):
            failing_session.commit()

        failing_session.rollback()
    finally:
        failing_session.close()

    verification_session = db_session_factory()

    try:
        result = verification_session.execute(
            select(records_table.c.value)
        ).scalars().all()

        assert result == ["unique record"]
    finally:
        verification_session.close()


def test_each_session_factory_call_creates_a_separate_session(
    db_session_factory: sessionmaker[Session],
) -> None:
    """Different requests can obtain independent SQLAlchemy sessions."""

    first_session = db_session_factory()
    second_session = db_session_factory()

    try:
        assert first_session is not second_session
    finally:
        first_session.close()
        second_session.close()
