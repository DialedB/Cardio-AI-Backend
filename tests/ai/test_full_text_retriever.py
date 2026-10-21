from unittest.mock import MagicMock, patch

import full_text_retriever
from full_text_retriever import FULL_TEXT_SEARCH_SQL, NeonFullTextRetriever


def make_engine_with_rows(rows):
    engine = MagicMock()
    connection = MagicMock()
    result = MagicMock()
    result.mappings.return_value = rows
    connection.execute.return_value = result
    engine.connect.return_value.__enter__.return_value = connection
    return engine, connection


def test_retriever_queries_neon_for_collection_and_maps_rows_to_documents():
    rows = [
        {
            "id": "chunk-1",
            "document": "Blood pressure can be managed with lifestyle changes.",
            "cmetadata": {"source": "guide.pdf", "page": 3},
            "rank": 0.9,
        },
        {"id": "chunk-2", "document": None, "cmetadata": None, "rank": 0.4},
    ]
    engine, connection = make_engine_with_rows(rows)
    retriever = NeonFullTextRetriever(
        collection_name="health-guides",
        connection_url="postgresql+psycopg://example/db",
        k=2,
    )

    with patch.object(full_text_retriever, "create_engine", return_value=engine) as create_engine:
        documents = retriever.invoke("high blood pressure")

    create_engine.assert_called_once_with(
        "postgresql+psycopg://example/db",
        pool_pre_ping=True,
    )
    sql, parameters = connection.execute.call_args.args
    assert str(sql) == str(FULL_TEXT_SEARCH_SQL)
    assert "websearch_to_tsquery('english', :query)" in str(sql)
    assert "c.name = :collection_name" in str(sql)
    assert parameters == {
        "collection_name": "health-guides",
        "query": "high blood pressure",
        "limit": 2,
    }
    assert [(document.id, document.page_content, document.metadata) for document in documents] == [
        (
            "chunk-1",
            "Blood pressure can be managed with lifestyle changes.",
            {"source": "guide.pdf", "page": 3},
        ),
        ("chunk-2", "", {}),
    ]


def test_retriever_returns_empty_list_when_neon_finds_no_matches():
    engine, _ = make_engine_with_rows([])
    retriever = NeonFullTextRetriever(
        connection_url="postgresql+psycopg://example/db",
    )

    with patch.object(full_text_retriever, "create_engine", return_value=engine):
        documents = retriever.invoke("no matching document")

    assert documents == []