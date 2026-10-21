"""Creation and readiness checks for Neon-backed full-text search."""

from pathlib import Path

from settings import get_neon_connection_url
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = Path(__file__).resolve().parent / "migrations" / "0001_add_full_text_search.sql"
REQUIRED_TABLE = "langchain_pg_embedding"
REQUIRED_COLUMN = "search_vector"
REQUIRED_INDEX = "langchain_pg_embedding_search_vector_gin"


def apply_full_text_search_migration() -> None:
    """Apply the checked-in, idempotent FTS migration to the configured Neon DB."""
    statements = [
        statement.strip()
        for statement in MIGRATION_PATH.read_text(encoding="utf-8").split(";")
        if statement.strip()
    ]
    engine = create_engine(get_neon_connection_url(), pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))
    finally:
        engine.dispose()


def require_full_text_search_schema() -> None:
    """Fail with setup instructions if the Neon FTS table, column, or index is absent."""
    engine = create_engine(get_neon_connection_url(), pool_pre_ping=True)
    try:
        inspector = inspect(engine)
        problems = []
        if not inspector.has_table(REQUIRED_TABLE):
            problems.append(f"table {REQUIRED_TABLE!r} is missing")
        else:
            columns = {column["name"] for column in inspector.get_columns(REQUIRED_TABLE)}
            if REQUIRED_COLUMN not in columns:
                problems.append(f"column {REQUIRED_COLUMN!r} is missing from {REQUIRED_TABLE!r}")
            indexes = {index["name"] for index in inspector.get_indexes(REQUIRED_TABLE)}
            if REQUIRED_INDEX not in indexes:
                problems.append(f"GIN index {REQUIRED_INDEX!r} is missing")

        if problems:
            details = "; ".join(problems)
            raise RuntimeError(
                "Neon full-text search schema is not ready: "
                f"{details}. Run the ingestion pipeline once to initialize PGVector "
                "and apply ai/migrations/0001_add_full_text_search.sql."
            )
    finally:
        engine.dispose()