"""The evaluation query set stays valid and the runner works without OpenAI or Neon."""

import json

import eval_queries
import pytest
from eval_queries import (
    EvalQuery,
    check_filters,
    load_queries,
    predict_filter_outcome,
    run_query,
)
from langchain_core.messages import AIMessage, HumanMessage
from rag_fakes import DRAFT, FakeRunnable, build_service, message
from rag_service import INSUFFICIENT_CONTEXT

QUERIES = load_queries()
# Categories whose queries must reach retrieval: the input filters should not stop them.
PASS_THROUGH_CATEGORIES = {"factual", "lay_wording", "follow_up", "off_corpus", "multilingual"}


def by_category(category):
    return [query for query in QUERIES if query.category == category]


def write_queries(path, *rows):
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return path


def test_query_file_covers_every_category() -> None:
    categories = {query.category for query in QUERIES}

    assert len(QUERIES) >= 60
    assert PASS_THROUGH_CATEGORIES <= categories
    assert {"scope_refusal", "injection", "empty", "false_refusal"} <= categories


def test_load_rejects_unknown_outcome(tmp_path) -> None:
    path = write_queries(
        tmp_path / "queries.jsonl",
        {"id": "a", "category": "factual", "question": "q", "expected_outcome": "maybe"},
    )

    with pytest.raises(ValueError, match="unknown expected_outcome"):
        load_queries(path)


def test_load_rejects_duplicate_ids(tmp_path) -> None:
    row = {"id": "a", "category": "factual", "question": "q", "expected_outcome": "answered"}
    path = write_queries(tmp_path / "queries.jsonl", row, row)

    with pytest.raises(ValueError, match="duplicate id"):
        load_queries(path)


def test_load_error_does_not_quote_the_question(tmp_path) -> None:
    path = tmp_path / "queries.jsonl"
    path.write_text('{"id": "a", "question": "a private question"', encoding="utf-8")

    with pytest.raises(ValueError) as error:
        load_queries(path)

    assert "private" not in str(error.value)


@pytest.mark.parametrize("query", by_category("injection"), ids=lambda query: query.id)
def test_injection_queries_are_caught_by_the_filter(query) -> None:
    assert predict_filter_outcome(query.question) == "safety_rejected"


@pytest.mark.parametrize("query", by_category("scope_refusal"), ids=lambda query: query.id)
def test_scope_queries_are_caught_by_the_filter(query) -> None:
    assert predict_filter_outcome(query.question) == "out_of_scope"


@pytest.mark.parametrize("query", by_category("empty"), ids=lambda query: query.id)
def test_empty_queries_are_caught_by_the_input_check(query) -> None:
    assert predict_filter_outcome(query.question) == "empty_input"


@pytest.mark.parametrize(
    "query",
    [query for query in QUERIES if query.category in PASS_THROUGH_CATEGORIES],
    ids=lambda query: query.id,
)
def test_ordinary_queries_pass_the_input_filters(query) -> None:
    assert predict_filter_outcome(query.question) is None


def test_run_query_records_a_matching_outcome() -> None:
    query = EvalQuery("q1", "factual", "How does exercise affect the heart?", "answered")

    row = run_query(build_service(), query)

    assert row["passed"] is True
    assert row["outcome"] == "answered"
    assert row["stage"] == "answer generation"
    assert row["sources"] == ["guide.pdf#p4"]
    assert row["answer"].startswith(DRAFT)
    assert row["declined_for_context"] is False


def test_run_query_fails_on_a_different_outcome_or_stage() -> None:
    service = build_service()
    wrong_outcome = EvalQuery("q1", "off_corpus", "A question", "insufficient_context")
    wrong_stage = EvalQuery("q2", "factual", "A question", "answered", "retrieval")

    assert run_query(service, wrong_outcome)["passed"] is False
    assert run_query(service, wrong_stage)["passed"] is False


def test_run_query_flags_an_answer_that_declines_in_words() -> None:
    service = build_service(model=FakeRunnable(message(INSUFFICIENT_CONTEXT)))

    row = run_query(service, EvalQuery("q1", "off_corpus", "A question", "insufficient_context"))

    assert row["outcome"] == "answered"
    assert row["declined_for_context"] is True


def test_run_query_passes_history_to_the_pipeline() -> None:
    model = FakeRunnable(message("standalone question"), message(DRAFT))
    history = (
        {"role": "user", "content": "What is atrial fibrillation?"},
        {"role": "assistant", "content": "An irregular heart rhythm."},
    )

    query = EvalQuery("q1", "follow_up", "Why?", "answered", history=history)
    run_query(build_service(model=model), query)

    reformulation_messages = model.calls[0]
    assert isinstance(reformulation_messages[1], HumanMessage)
    assert isinstance(reformulation_messages[2], AIMessage)
    assert reformulation_messages[2].content == "An irregular heart rhythm."


def test_check_filters_leaves_pass_through_queries_undecided() -> None:
    row = check_filters(EvalQuery("q1", "factual", "What is hypertension?", "answered"))

    assert row["passed"] is None
    assert row["outcome"] == "not_run"


def test_check_filters_fails_a_refusal_the_filter_missed() -> None:
    query = EvalQuery("q1", "scope_gap", "Give me a treatment plan.", "out_of_scope")

    assert check_filters(query)["passed"] is False


def test_main_filters_only_writes_results_and_summary(tmp_path, capsys) -> None:
    exit_code = eval_queries.main(["--filters-only", "--out", str(tmp_path)])

    (run_dir,) = tmp_path.iterdir()
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines()]
    assert exit_code == 0
    assert len(rows) == len(QUERIES)
    assert "## By category" in (run_dir / "summary.md").read_text()
    assert "filters only" in capsys.readouterr().out


def test_main_live_mode_runs_the_selected_queries(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        eval_queries.RagService, "from_settings", classmethod(lambda cls: build_service())
    )

    exit_code = eval_queries.main(["--category", "factual", "--limit", "2", "--out", str(tmp_path)])

    (run_dir,) = tmp_path.iterdir()
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines()]
    assert exit_code == 0
    assert [row["outcome"] for row in rows] == ["answered", "answered"]
    assert "Latency" in (run_dir / "summary.md").read_text()


def test_main_reports_a_startup_failure(tmp_path, monkeypatch, capsys) -> None:
    def fail(cls):
        raise RuntimeError("DATABASE_URL is missing")

    monkeypatch.setattr(eval_queries.RagService, "from_settings", classmethod(fail))

    assert eval_queries.main(["--limit", "1", "--out", str(tmp_path)]) == 1
    assert "failed to start" in capsys.readouterr().out
    assert not list(tmp_path.iterdir())
