"""Compare sync and async embedding throughput without writing to Neon.

This establishes the current ingestion baseline. Each run sends the selected
texts to the configured embedding API and may incur API charges.
"""

import argparse
import asyncio
import json
from statistics import mean
from time import perf_counter

from settings import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_CONCURRENCY,
    EMBEDDING_MODEL,
    get_embeddings,
)


def run_sync_benchmark(texts, embeddings, *, batch_size, repeats=1):
    """Embed a fixed corpus repeatedly and return per-run timings."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    if not texts:
        raise ValueError("texts must contain at least one item")

    batches = [texts[start : start + batch_size] for start in range(0, len(texts), batch_size)]
    runs = []
    for run_number in range(1, repeats + 1):
        started = perf_counter()
        embedded_count = 0
        for batch in batches:
            vectors = embeddings.embed_documents(batch)
            if len(vectors) != len(batch):
                raise RuntimeError(
                    f"Embedding returned {len(vectors)} vectors for {len(batch)} texts"
                )
            embedded_count += len(vectors)
        elapsed = perf_counter() - started
        runs.append(
            {
                "run": run_number,
                "elapsed_seconds": round(elapsed, 3),
                "texts_per_second": round(embedded_count / elapsed, 2) if elapsed else None,
                "embedded_texts": embedded_count,
                "api_batches": len(batches),
            }
        )

    return {
        "mode": "sync",
        "model": EMBEDDING_MODEL,
        "selected_texts": len(texts),
        "batch_size": batch_size,
        "runs": runs,
        "mean_elapsed_seconds": round(mean(run["elapsed_seconds"] for run in runs), 3),
    }


async def _embed_batches_async(batches, embeddings, concurrency):
    async def embed_batch(batch):
        vectors = await embeddings.aembed_documents(batch)
        if len(vectors) != len(batch):
            raise RuntimeError(
                f"Embedding returned {len(vectors)} vectors for {len(batch)} texts"
            )
        return len(vectors)

    embedded_count = 0
    for start in range(0, len(batches), concurrency):
        group = batches[start : start + concurrency]
        embedded_count += sum(await asyncio.gather(*(embed_batch(batch) for batch in group)))
    return embedded_count


def run_async_benchmark(texts, embeddings, *, batch_size, concurrency, repeats=1):
    """Benchmark async embedding with a bounded number of concurrent batches."""
    if batch_size < 1 or concurrency < 1:
        raise ValueError("batch_size and concurrency must be at least 1")
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    if not texts:
        raise ValueError("texts must contain at least one item")

    batches = [texts[start : start + batch_size] for start in range(0, len(texts), batch_size)]

    async def run_all():
        runs = []
        for run_number in range(1, repeats + 1):
            started = perf_counter()
            embedded_count = await _embed_batches_async(batches, embeddings, concurrency)
            elapsed = perf_counter() - started
            runs.append(
                {
                    "run": run_number,
                    "elapsed_seconds": round(elapsed, 3),
                    "texts_per_second": round(embedded_count / elapsed, 2)
                    if elapsed
                    else None,
                    "embedded_texts": embedded_count,
                    "api_batches": len(batches),
                }
            )
        return runs

    runs = asyncio.run(run_all())

    return {
        "mode": "async",
        "model": EMBEDDING_MODEL,
        "selected_texts": len(texts),
        "batch_size": batch_size,
        "concurrency": concurrency,
        "runs": runs,
        "mean_elapsed_seconds": round(mean(run["elapsed_seconds"] for run in runs), 3),
    }


def load_benchmark_texts(max_chunks):
    """Load and split the local PDF corpus, keeping distinct chunk text only."""
    from ingestion_pipeline import load_documents, prepare_chunks, split_documents

    chunks = prepare_chunks(split_documents(load_documents()))
    texts = list(dict.fromkeys(chunk.page_content for chunk in chunks))
    if max_chunks is not None:
        texts = texts[:max_chunks]
    if not texts:
        raise RuntimeError("No chunk text is available to benchmark")
    return texts


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare embedding modes; no Neon reads or writes are performed."
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=100,
        help="Maximum distinct PDF chunks to embed per run (default: 100).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=EMBEDDING_BATCH_SIZE,
        help=f"Texts per embedding call (default: {EMBEDDING_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Number of times to embed the same selected text (default: 1).",
    )
    parser.add_argument(
        "--mode",
        choices=("compare", "sync", "async"),
        default="compare",
        help="Benchmark sync, async, or both (default: compare).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=EMBEDDING_CONCURRENCY,
        help=f"Concurrent async embedding batches (default: {EMBEDDING_CONCURRENCY}).",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.max_chunks is not None and args.max_chunks < 1:
        raise SystemExit("--max-chunks must be at least 1")
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be at least 1")
    if args.repeats < 1:
        raise SystemExit("--repeats must be at least 1")
    if args.concurrency < 1:
        raise SystemExit("--concurrency must be at least 1")

    texts = load_benchmark_texts(args.max_chunks)
    embeddings = get_embeddings()
    if args.mode == "sync":
        result = run_sync_benchmark(
            texts, embeddings, batch_size=args.batch_size, repeats=args.repeats
        )
    elif args.mode == "async":
        result = run_async_benchmark(
            texts,
            embeddings,
            batch_size=args.batch_size,
            concurrency=args.concurrency,
            repeats=args.repeats,
        )
    else:
        sync_result = run_sync_benchmark(
            texts, embeddings, batch_size=args.batch_size, repeats=args.repeats
        )
        async_result = run_async_benchmark(
            texts,
            embeddings,
            batch_size=args.batch_size,
            concurrency=args.concurrency,
            repeats=args.repeats,
        )
        sync_seconds = sync_result["mean_elapsed_seconds"]
        async_seconds = async_result["mean_elapsed_seconds"]
        result = {
            "mode": "compare",
            "sync": sync_result,
            "async": async_result,
            "async_speedup": round(sync_seconds / async_seconds, 3) if async_seconds else None,
        }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
