"""ingestion_pipeline: content-addressed chunk IDs, deduplication, and async embedding."""

import asyncio
from pathlib import Path

import pytest
from ingestion_pipeline import chunk_id, content_hash, embed_and_write_batches, prepare_chunks
from langchain_core.documents import Document


def make_chunk(source, content, *, page=0):
    return Document(
        page_content=content,
        metadata={"source": str(source), "page": page},
    )


def test_chunk_id_is_stable_and_independent_of_page_position():
    digest = content_hash("A stable chunk of text.")

    first = chunk_id("guide.pdf", digest, "health-guides")
    same_content_at_later_page = chunk_id("guide.pdf", digest, "health-guides")

    assert first == same_content_at_later_page
    assert first != chunk_id("other-guide.pdf", digest, "health-guides")
    assert first != chunk_id("guide.pdf", content_hash("Different text."), "health-guides")
    assert first != chunk_id("guide.pdf", digest, "another-collection")


def test_prepare_chunks_collapses_duplicate_content_from_same_source():
    docs_dir = Path("test-docs")
    source = docs_dir / "guide.pdf"
    content = "The same chunk appears twice."
    chunks = [
        make_chunk(source, content, page=0),
        make_chunk(source, content, page=4),
    ]

    prepared = prepare_chunks(chunks, docs_dir=docs_dir, collection_name="health-guides")

    assert len(prepared) == 1
    assert prepared[0].metadata["source_key"] == "guide.pdf"
    assert prepared[0].metadata["content_sha256"] == content_hash(content)
    assert prepared[0].id == chunk_id(
        "guide.pdf",
        content_hash(content),
        "health-guides",
    )


def test_prepare_chunks_keeps_identical_content_from_different_sources():
    docs_dir = Path("test-docs")
    content = "The same text appears in two source files."
    chunks = [
        make_chunk(docs_dir / "first.pdf", content),
        make_chunk(docs_dir / "second.pdf", content),
    ]

    prepared = prepare_chunks(chunks, docs_dir=docs_dir, collection_name="health-guides")

    assert len(prepared) == 2
    assert {chunk.metadata["source_key"] for chunk in prepared} == {
        "first.pdf",
        "second.pdf",
    }
    assert len({chunk.id for chunk in prepared}) == 2
    assert {chunk.metadata["content_sha256"] for chunk in prepared} == {
        content_hash(content)
    }


class FakeEmbeddings:
    def __init__(self):
        self.active = 0
        self.max_active = 0

    async def aembed_documents(self, texts):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.02)
            return [[float(len(text))] for text in texts]
        finally:
            self.active -= 1


class FakeVectorStore:
    def __init__(self):
        self.rows = []

    def add_embeddings(self, *, texts, embeddings, metadatas, ids):
        self.rows.extend(zip(ids, texts, embeddings, metadatas, strict=True))


def chunk(identifier, content):
    return Document(id=identifier, page_content=content, metadata={"source": "test.pdf"})


async def test_embedding_batches_run_concurrently_and_write_all_chunks():
    embeddings = FakeEmbeddings()
    vector_store = FakeVectorStore()
    chunks_by_hash = {
        "hash-one": [chunk("one", "first text"), chunk("one-copy", "first text")],
        "hash-two": [chunk("two", "second")],
        "hash-three": [chunk("three", "third text")],
    }

    embedding_wall, worker_time, write_time, saved = await embed_and_write_batches(
        embeddings,
        vector_store,
        chunks_by_hash,
        batch_size=1,
        concurrency=2,
    )

    assert embeddings.max_active == 2
    assert saved == 4
    assert len(vector_store.rows) == 4
    assert {row[0] for row in vector_store.rows} == {"one", "one-copy", "two", "three"}
    assert embedding_wall > 0
    assert worker_time >= embedding_wall
    assert write_time >= 0


async def test_embedding_result_count_mismatch_fails_before_writing():
    class IncompleteEmbeddings:
        async def aembed_documents(self, _texts):
            return []

    vector_store = FakeVectorStore()
    chunks_by_hash = {"hash-one": [chunk("one", "first text")]}

    with pytest.raises(RuntimeError, match="Embedding returned 0 vectors"):
        await embed_and_write_batches(
            IncompleteEmbeddings(), vector_store, chunks_by_hash, batch_size=1, concurrency=1
        )

    assert vector_store.rows == []
