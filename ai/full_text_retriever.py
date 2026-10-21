"""Postgres full-text retriever for the shared LangChain PGVector table."""

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import PrivateAttr
from settings import COLLECTION_NAME, get_neon_connection_url
from sqlalchemy import Engine, create_engine, text

FULL_TEXT_SEARCH_SQL = text(
    """
    SELECT e.id, e.document, e.cmetadata,
           ts_rank_cd(e.search_vector, websearch_to_tsquery('english', :query)) AS rank
    FROM langchain_pg_embedding AS e
    JOIN langchain_pg_collection AS c ON c.uuid = e.collection_id
    WHERE c.name = :collection_name
      AND e.search_vector @@ websearch_to_tsquery('english', :query)
    ORDER BY rank DESC
    LIMIT :limit
    """
)


class NeonFullTextRetriever(BaseRetriever):
    """Retrieve relevant ingested chunks with Postgres full-text search."""

    collection_name: str = COLLECTION_NAME
    connection_url: str = ""
    k: int = 5

    _engine: Engine | None = PrivateAttr(default=None)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        if self._engine is None:
            self._engine = create_engine(
                self.connection_url or get_neon_connection_url(),
                pool_pre_ping=True,
            )

        with self._engine.connect() as connection:
            rows = connection.execute(
                FULL_TEXT_SEARCH_SQL,
                {
                    "collection_name": self.collection_name,
                    "query": query,
                    "limit": self.k,
                },
            ).mappings()
            return [
                Document(
                    id=row["id"],
                    page_content=row["document"] or "",
                    metadata=dict(row["cmetadata"] or {}),
                )
                for row in rows
            ]
