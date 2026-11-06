import pytest
from ai.benchmark_embeddings import run_async_benchmark, run_sync_benchmark


class FakeEmbeddings:
    def __init__(self):
        self.batches = []

    def embed_documents(self, texts):
        self.batches.append(list(texts))
        return [[float(len(text))] for text in texts]

    async def aembed_documents(self, texts):
        self.batches.append(list(texts))
        return [[float(len(text))] for text in texts]


def test_sync_benchmark_batches_fixed_texts_for_each_repeat():
    embeddings = FakeEmbeddings()

    result = run_sync_benchmark(
        ["one", "two", "three"], embeddings, batch_size=2, repeats=2
    )

    assert embeddings.batches == [
        ["one", "two"],
        ["three"],
        ["one", "two"],
        ["three"],
    ]
    assert result["mode"] == "sync"
    assert result["selected_texts"] == 3
    assert [run["embedded_texts"] for run in result["runs"]] == [3, 3]
    assert [run["api_batches"] for run in result["runs"]] == [2, 2]


@pytest.mark.parametrize(
    ("texts", "batch_size", "repeats"),
    [([], 2, 1), (["text"], 0, 1), (["text"], 1, 0)],
)
def test_sync_benchmark_rejects_invalid_input(texts, batch_size, repeats):
    with pytest.raises(ValueError):
        run_sync_benchmark(texts, FakeEmbeddings(), batch_size=batch_size, repeats=repeats)


def test_sync_benchmark_rejects_incomplete_embedding_results():
    class IncompleteEmbeddings:
        def embed_documents(self, _texts):
            return []

    with pytest.raises(RuntimeError, match="vectors for"):
        run_sync_benchmark(["text"], IncompleteEmbeddings(), batch_size=1)


def test_async_benchmark_uses_same_texts_and_reports_concurrency():
    embeddings = FakeEmbeddings()

    result = run_async_benchmark(
        ["one", "two", "three"],
        embeddings,
        batch_size=1,
        concurrency=2,
        repeats=2,
    )

    assert embeddings.batches == [["one"], ["two"], ["three"]] * 2
    assert result["mode"] == "async"
    assert result["concurrency"] == 2
    assert [run["embedded_texts"] for run in result["runs"]] == [3, 3]
