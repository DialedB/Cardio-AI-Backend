"""Shared Neon and embedding settings for ingestion and RAG."""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent
DOCS_DIR = PIPELINE_DIR / "docs"

# Load environment variables in precedence order: process environment, the
# repo-root .env.local, then pipeline-local files without overriding earlier values.
load_dotenv(PROJECT_ROOT / ".env.local")
load_dotenv(PIPELINE_DIR / ".env.local", override=False)
load_dotenv(PIPELINE_DIR / ".env", override=False)

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
COLLECTION_NAME = os.getenv("NEON_VECTOR_COLLECTION", "ai_health_documents_v3")
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "100"))
EMBEDDING_BATCH_SIZE = max(1, int(os.getenv("EMBEDDING_BATCH_SIZE", "1000")))
EMBEDDING_CONCURRENCY = max(1, int(os.getenv("EMBEDDING_CONCURRENCY", "4")))
NEON_WRITE_BATCH_SIZE = max(1, int(os.getenv("NEON_WRITE_BATCH_SIZE", "500")))
# Query-time OpenAI calls: a stalled request raises after the timeout instead of hanging.
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))
OPENAI_MAX_RETRIES = max(0, int(os.getenv("OPENAI_MAX_RETRIES", "2")))
RAG_MODEL_NAME = os.getenv("RAG_MODEL_NAME", "gpt-4o-mini")
SAFETY_REVIEW_MODEL = os.getenv("SAFETY_REVIEW_MODEL", "gpt-4o-mini")
# Most recent chat messages sent to the models with each question.
RAG_MAX_HISTORY_MESSAGES = max(1, int(os.getenv("RAG_MAX_HISTORY_MESSAGES", "20")))


def get_embeddings() -> OpenAIEmbeddings:
    """Return configured OpenAIEmbeddings with batching enabled."""
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        chunk_size=EMBEDDING_BATCH_SIZE,
    )


def get_neon_connection_url() -> str:
    """Return the direct Neon URL in psycopg 3 SQLAlchemy URL format."""
    # This is a long-running local process, and PGVector initializes schema
    # objects on connect; prefer Neon’s direct URL for that session-sensitive work.
    url = os.getenv("DATABASE_URL_UNPOOLED") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is missing. Link the Neon project and pull its variables "
            "into the project-root .env.local file."
        )

    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql+psycopg://" + url[len("postgresql+psycopg2://") :]
    return url
