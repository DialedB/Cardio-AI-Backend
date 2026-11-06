import asyncio

import pytest
from ingestion_pipeline import embed_and_write_batches
from langchain_core.documents import Document


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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
