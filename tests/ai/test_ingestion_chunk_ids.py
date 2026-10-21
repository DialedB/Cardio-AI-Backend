from pathlib import Path

from ingestion_pipeline import chunk_id, content_hash, prepare_chunks
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