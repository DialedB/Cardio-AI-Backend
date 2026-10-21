import argparse
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from full_text_schema import apply_full_text_search_migration
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter
from settings import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION_NAME,
    DOCS_DIR,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MODEL,
    NEON_WRITE_BATCH_SIZE,
    get_embeddings,
    get_neon_connection_url,
)
from sqlalchemy import create_engine, inspect, text

# PGVector (langchain-postgres 0.0.19) schema: langchain_pg_embedding rows
# belong to a langchain_pg_collection via collection_id -> uuid.
EXISTING_IDS_SQL = text(
    """
    SELECT e.id
    FROM langchain_pg_embedding AS e
    JOIN langchain_pg_collection AS c ON c.uuid = e.collection_id
    WHERE c.name = :collection_name
    """
)


def load_documents(docs_path=DOCS_DIR):
    """Load all PDF documents (one Document per page) in sorted file order."""
    docs_path = Path(docs_path)
    if not docs_path.exists():
        raise FileNotFoundError(f"The documents directory does not exist: {docs_path}")

    pdf_paths = sorted(docs_path.glob("*.pdf"), key=lambda path: path.name)
    if not pdf_paths:
        raise FileNotFoundError(f"No .pdf files found in {docs_path}.")

    documents = []
    for pdf_path in pdf_paths:
        documents.extend(PyPDFLoader(str(pdf_path)).load())

    print(f"Loaded {len(documents)} pages from {len(pdf_paths)} PDFs in {docs_path}.")
    return documents


def split_documents(documents, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP):
    """Split source documents into retrieval-sized chunks."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = splitter.split_documents(documents)
    print(f"Split {len(documents)} pages into {len(chunks)} chunks.")
    return chunks


def content_hash(content):
    """Return the hex SHA-256 of chunk text."""
    return sha256(content.encode("utf-8")).hexdigest()


def source_key_for(document, docs_dir=DOCS_DIR):
    """Return the document source path relative to the docs directory."""
    source = Path(document.metadata.get("source", "unknown"))
    try:
        return source.resolve().relative_to(Path(docs_dir).resolve()).as_posix()
    except ValueError:
        return source.name


def chunk_id(source_key, digest, collection_name=COLLECTION_NAME):
    """Content-addressed ID: stable across file order, page shifts and reruns.

    Includes the collection name because langchain_pg_embedding.id is a global
    primary key, so identical chunks in two collections must not share an ID.
    """
    return str(uuid5(NAMESPACE_URL, f"{collection_name}:{source_key}:{digest}"))


def prepare_chunks(chunks, docs_dir=DOCS_DIR, collection_name=COLLECTION_NAME):
    """Assign IDs and metadata; collapse identical text within the same source."""
    prepared = {}
    for chunk in chunks:
        source_key = source_key_for(chunk, docs_dir)
        digest = content_hash(chunk.page_content)
        identifier = chunk_id(source_key, digest, collection_name)
        if identifier in prepared:
            continue
        metadata = {**chunk.metadata, "source_key": source_key, "content_sha256": digest}
        prepared[identifier] = Document(
            id=identifier, page_content=chunk.page_content, metadata=metadata
        )
    return list(prepared.values())


def estimate_tokens(texts):
    """Estimate embedding tokens, using tiktoken when it is available offline."""
    try:
        import tiktoken

        try:
            encoding = tiktoken.encoding_for_model(EMBEDDING_MODEL)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        return sum(len(encoding.encode(content)) for content in texts)
    except Exception:
        return sum(len(content) for content in texts) // 4


def fetch_existing_ids():
    """Return the IDs of every row stored in the collection."""
    engine = create_engine(get_neon_connection_url())
    try:
        if not inspect(engine).has_table("langchain_pg_embedding"):
            return set()
        with engine.connect() as connection:
            rows = connection.execute(EXISTING_IDS_SQL, {"collection_name": COLLECTION_NAME})
            return {row_id for (row_id,) in rows}
    finally:
        engine.dispose()


def write_chunks(vector_store, chunks, embeddings_by_id):
    """Upsert chunks with precomputed embeddings in bounded Neon batches."""
    for start in range(0, len(chunks), NEON_WRITE_BATCH_SIZE):
        batch = chunks[start : start + NEON_WRITE_BATCH_SIZE]
        vector_store.add_embeddings(
            texts=[chunk.page_content for chunk in batch],
            embeddings=[embeddings_by_id[chunk.id] for chunk in batch],
            metadatas=[chunk.metadata for chunk in batch],
            ids=[chunk.id for chunk in batch],
        )


def create_vector_store(chunks, prune=True, dry_run=False):
    """Embed only new chunks, upsert them into Neon, then prune stale rows."""
    lookup_start = perf_counter()
    existing_ids = fetch_existing_ids()
    lookup_seconds = perf_counter() - lookup_start

    current_ids = {chunk.id for chunk in chunks}
    pending = [chunk for chunk in chunks if chunk.id not in existing_ids]
    stale = sorted(existing_ids - current_ids)
    # Identical text in several sources is embedded once and shared.
    chunks_by_hash = {}
    for chunk in pending:
        chunks_by_hash.setdefault(chunk.metadata["content_sha256"], []).append(chunk)
    texts_by_hash = {digest: group[0].page_content for digest, group in chunks_by_hash.items()}

    print(
        f"Collection '{COLLECTION_NAME}': {len(chunks)} chunks; "
        f"unchanged={len(chunks) - len(pending)}; new={len(pending)} "
        f"({len(texts_by_hash)} distinct texts to embed); stale={len(stale)}."
    )
    print(f"Estimated embedding tokens: {estimate_tokens(texts_by_hash.values())}.")

    if dry_run:
        print("Dry run: nothing written, no embeddings requested.")
        return None

    store_start = perf_counter()
    embeddings = get_embeddings()
    vector_store = PGVector(
        embeddings=embeddings,
        collection_name=COLLECTION_NAME,
        connection=get_neon_connection_url(),
        use_jsonb=True,
    )
    # PGVector creates its base tables here; ensure the same database also has
    # the FTS generated column and GIN index before ingestion writes any chunks.
    apply_full_text_search_migration()
    store_init_seconds = perf_counter() - store_start

    if not pending and (not prune or not stale):
        print(f"Neon collection '{COLLECTION_NAME}' is already up to date.")
        return vector_store

    embedding_seconds = 0.0
    write_seconds = 0.0
    hashes = list(texts_by_hash)
    saved_chunks = 0
    for embed_start in range(0, len(hashes), EMBEDDING_BATCH_SIZE):
        batch_hashes = hashes[embed_start : embed_start + EMBEDDING_BATCH_SIZE]
        embed_started = perf_counter()
        batch_embeddings = embeddings.embed_documents(
            [texts_by_hash[digest] for digest in batch_hashes]
        )
        embedding_seconds += perf_counter() - embed_started

        batch_chunks = []
        embeddings_by_id = {}
        for digest, vector in zip(batch_hashes, batch_embeddings, strict=False):
            for chunk in chunks_by_hash[digest]:
                batch_chunks.append(chunk)
                embeddings_by_id[chunk.id] = vector

        write_started = perf_counter()
        write_chunks(vector_store, batch_chunks, embeddings_by_id)
        write_seconds += perf_counter() - write_started
        saved_chunks += len(batch_chunks)
        saved = min(embed_start + len(batch_hashes), len(hashes))
        print(f"Embedded {saved}/{len(hashes)} texts; saved {saved_chunks} chunks.")

    prune_seconds = 0.0
    if prune and stale:
        prune_started = perf_counter()
        for start in range(0, len(stale), NEON_WRITE_BATCH_SIZE):
            vector_store.delete(
                ids=stale[start : start + NEON_WRITE_BATCH_SIZE],
                collection_only=True,
            )
        prune_seconds = perf_counter() - prune_started
        print(f"Deleted {len(stale)} stale chunks.")
    elif stale:
        print(f"Skipped deleting {len(stale)} stale chunks (--no-prune).")

    print(
        f"Upserted {len(pending)} new chunks into Neon collection '{COLLECTION_NAME}' "
        f"({len(chunks) - len(pending)} unchanged)."
    )
    print(
        f"Timing: store setup={store_init_seconds:.2f}s; "
        f"existing-ID lookup={lookup_seconds:.2f}s; embeddings={embedding_seconds:.2f}s; "
        f"Neon writes={write_seconds:.2f}s; prune={prune_seconds:.2f}s."
    )
    return vector_store


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Ingest docs/*.pdf into Neon pgvector.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned counts and estimated tokens without writing or embedding.",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="Do not delete stored chunks that this run no longer produces.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    start_time = perf_counter()
    load_start = perf_counter()
    documents = load_documents()
    load_seconds = perf_counter() - load_start
    split_start = perf_counter()
    chunks = prepare_chunks(split_documents(documents))
    split_seconds = perf_counter() - split_start
    if not chunks:
        raise RuntimeError("Loading and splitting produced zero chunks; refusing to continue.")

    create_vector_store(chunks, prune=not args.no_prune, dry_run=args.dry_run)
    end_time = perf_counter()
    print(
        f"Timing: document loading={load_seconds:.2f}s; "
        f"chunking={split_seconds:.2f}s; "
        f"total={end_time - start_time:.2f}s."
    )

if __name__ == "__main__":
    main()