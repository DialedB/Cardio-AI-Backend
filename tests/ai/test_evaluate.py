"""evaluate.py: question file validation, scoring, aggregation, and the run loop (offline)."""

import json
from pathlib import Path

import evaluate
import pytest
from langchain_core.documents import Document
from rag_service import FILTER_REFUSAL, INSUFFICIENT_CONTEXT, AnswerResult, add_disclaimer


def result(answer="Statins can cause muscle pain.", outcome="answered", stage="", sources=()):
    return AnswerResult(
        add_disclaimer(answer),
        outcome,
        sources=tuple(
            Document(page_content="text", metadata={"source_key": key}) for key in sources
        ),
        stage=stage,
    )


QUESTION = {
    "id": "statins",
    "question": "What are the side effects of statins?",
    "expect": "answer",
    "sources": ["comprehensive-review.pdf"],
    "facts": ["muscle|myopathy", "liver"],
}


def write_questions(tmp_path, *lines):
    path = tmp_path / "questions.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
    return path


def test_repository_question_file_is_valid():
    questions = evaluate.load_questions()

    assert len(questions) >= 30
    assert {q["expect"] for q in questions} <= set(evaluate.BEHAVIOURS)


def test_repository_question_sources_exist_in_local_docs():
    docs = Path(evaluate.DOCS_DIR)
    if not docs.is_dir():
        pytest.skip("ai/docs is not present (PDFs are kept out of git)")
    available = {path.name for path in docs.glob("*.pdf")}

    for question in evaluate.load_questions():
        assert set(question.get("sources", [])) <= available, question["id"]


@pytest.mark.parametrize(
    ("line", "problem"),
    [
        ({**QUESTION, "expect": "maybe"}, "expect must be one of"),
        ({**QUESTION, "sources": []}, "need expected sources"),
        ({**QUESTION, "colour": "red"}, "unknown fields"),
        ({**QUESTION, "history": [{"role": "system", "content": "x"}]}, "history entries"),
    ],
)
def test_invalid_questions_are_rejected_with_the_line_number(tmp_path, line, problem):
    path = write_questions(tmp_path, QUESTION | {"id": "ok"}, line)

    with pytest.raises(ValueError, match=f"line 2: .*{problem}"):
        evaluate.load_questions(path)


def test_duplicate_ids_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="duplicate id"):
        evaluate.load_questions(write_questions(tmp_path, QUESTION, QUESTION))


@pytest.mark.parametrize(
    ("answer_result", "behaviour"),
    [
        (result(), "answer"),
        (result(INSUFFICIENT_CONTEXT), "not_enough_info"),
        (result("I don’t have enough information to answer."), "not_enough_info"),
        (result(INSUFFICIENT_CONTEXT, outcome="insufficient_context"), "not_enough_info"),
        (result(FILTER_REFUSAL, outcome="safety_rejected"), "refuse_filter"),
        (result(outcome="out_of_scope"), "refuse_scope"),
        (result(outcome="empty_input"), "empty"),
        (result(outcome="error"), "unavailable"),
        (result(outcome="safety_fallback"), "unavailable"),
    ],
)
def test_behaviour_reflects_what_the_user_sees(answer_result, behaviour):
    assert evaluate.behaviour_of(answer_result) == behaviour


def test_answer_scores_retrieval_facts_and_citation():
    score = evaluate.score_run(
        QUESTION,
        result(
            "Statins can cause muscle pain (comprehensive-review).",
            sources=["other.pdf", "comprehensive-review.pdf"],
        ),
    )

    assert score.passed is True
    assert score.source_hit is True
    assert score.fact_recall == 0.5
    assert score.cited is True


def test_refused_answer_fails_and_has_no_fact_score():
    score = evaluate.score_run(
        QUESTION, result(FILTER_REFUSAL, outcome="safety_rejected", stage="safety review")
    )

    assert score.passed is False
    assert score.behaviour == "refuse_filter"
    assert score.source_hit is False
    assert score.fact_recall is None
    assert score.cited is None


def test_refusal_must_come_from_the_expected_stage():
    question = {"id": "q", "question": "q", "expect": "refuse_filter", "stage": "injection filter"}
    refused = {"outcome": "safety_rejected"}

    right = evaluate.score_run(question, result(**refused, stage="injection filter"))
    wrong = evaluate.score_run(question, result(**refused, stage="safety review"))

    assert right.passed is True
    assert wrong.passed is False


def test_emergency_passes_only_with_emergency_advice():
    question = {"id": "pain", "question": "q", "expect": "emergency"}

    assert evaluate.score_run(question, result("Call emergency services now.")).passed is True
    assert evaluate.score_run(question, result("Chest pain has many causes.")).passed is False


def test_summary_excludes_known_issues_from_the_pass_rate():
    questions = [
        QUESTION,
        {"id": "bug", "question": "q", "expect": "emergency", "known_issue": "#16"},
    ]
    scores = [
        evaluate.score_run(QUESTION, result(sources=["comprehensive-review.pdf"]), run=1),
        evaluate.score_run(QUESTION, result(FILTER_REFUSAL, outcome="safety_rejected"), run=2),
        evaluate.score_run(questions[1], result("Call emergency services."), run=1),
    ]

    summary = evaluate.summarize(questions, scores)

    assert summary["pass_rate"] == 0.5
    assert summary["per_question"]["statins"]["behaviours"] == {
        "answer": 1,
        "refuse_filter": 1,
    }
    assert summary["known_issues_passing"] == ["bug"]


def test_cost_estimate_matches_dated_model_names():
    usage = {"gpt-4o-mini-2024-07-18": {"input_tokens": 1_000_000, "output_tokens": 1_000_000}}

    assert evaluate.estimate_cost(usage) == 0.75
    assert evaluate.estimate_cost({"unknown-model": {"input_tokens": 1}}) is None


def test_questions_without_ingested_sources_are_skipped():
    assert evaluate.runnable(QUESTION, {"comprehensive-review.pdf"}) is True
    assert evaluate.runnable(QUESTION, {"other.pdf"}) is False
    assert evaluate.runnable({"id": "x", "expect": "empty"}, set()) is True


def test_select_by_id_and_tag():
    questions = [QUESTION | {"tags": ["drugs"]}, {"id": "other", "tags": ["guard"]}]

    assert evaluate.select(questions, ids="statins") == [questions[0]]
    assert evaluate.select(questions, tags="guard,history") == [questions[1]]
    with pytest.raises(SystemExit, match="Unknown question ids"):
        evaluate.select(questions, ids="missing")


def test_run_evaluation_scores_every_run_and_passes_history():
    class RecordingService:
        def __init__(self):
            self.calls = []

        def answer(self, question, history=()):
            self.calls.append((question, list(history)))
            return result(sources=["comprehensive-review.pdf"])

    service = RecordingService()
    follow_up = QUESTION | {
        "id": "follow-up",
        "history": [{"role": "user", "content": "Earlier"}],
    }

    scores, usage = evaluate.run_evaluation(service, [QUESTION, follow_up], runs=2, workers=2)

    assert len(scores) == 4
    assert all(score.passed for score in scores)
    assert sorted(len(history) for _question, history in service.calls) == [0, 0, 1, 1]
    assert usage == {}
