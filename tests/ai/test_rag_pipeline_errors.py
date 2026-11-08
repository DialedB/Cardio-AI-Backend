"""Fail-closed and fallback behavior when a RagService pipeline step fails."""

import pytest
import rag_service
from langchain_core.messages import AIMessage, HumanMessage
from rag_fakes import DRAFT, QUESTION, SOURCE, FakeModeration, FakeRunnable, build_service, message
from rag_service import CHECK_UNAVAILABLE, add_disclaimer

UNAVAILABLE = add_disclaimer(CHECK_UNAVAILABLE)


def assert_failed_closed(result, outcome="error", stage=None):
    assert result.answer == UNAVAILABLE
    assert result.outcome == outcome
    assert result.record_in_history is False
    assert result.review_approved is None
    if stage is not None:
        assert result.stage == stage


def test_successful_question_is_answered_and_recordable():
    result = build_service().answer(QUESTION)

    assert result.answer == add_disclaimer(DRAFT)
    assert result.outcome == "answered"
    assert result.record_in_history is True
    assert result.review_approved is True


def test_input_moderation_failure_fails_closed_before_any_model_call():
    def outage(_text):
        raise ConnectionError("moderation unavailable")

    model = FakeRunnable(message(DRAFT))
    service = build_service(moderation_client=FakeModeration(outage), model=model)

    result = service.answer(QUESTION)

    assert_failed_closed(result, outcome="safety_fallback", stage="input moderation")
    assert model.calls == []


def test_retrieval_failure_fails_closed():
    service = build_service(retriever=FakeRunnable(ConnectionError("Neon unavailable")))

    assert_failed_closed(service.answer(QUESTION), stage="retrieval")


def test_fusion_failure_fails_closed(monkeypatch):
    def broken_fusion(*_args, **_kwargs):
        raise ValueError("bad results")

    monkeypatch.setattr(rag_service, "reciprocal_rank_fusion", broken_fusion)

    assert_failed_closed(build_service().answer(QUESTION), stage="fusion")


def test_generation_failure_fails_closed():
    service = build_service(model=FakeRunnable(TimeoutError("request timed out")))

    assert_failed_closed(service.answer(QUESTION), stage="generation")


def test_text_blocks_are_joined_into_the_answer():
    service = build_service(
        model=FakeRunnable(
            message(
                [
                    {"type": "reasoning", "reasoning": "internal"},
                    {"type": "text", "text": "Exercise helps "},
                    "the heart.",
                    {"type": "text", "text": None},
                ]
            )
        )
    )

    result = service.answer(QUESTION)

    assert result.answer == add_disclaimer("Exercise helps the heart.")
    assert result.record_in_history is True


@pytest.mark.parametrize(
    "content",
    [
        "",
        "   ",
        None,
        [],
        [{"type": "reasoning", "reasoning": "internal"}],
        [{"type": "text", "text": 42}, {"type": "text"}, {"text": "missing type"}],
        [{"type": "text", "text": "   "}],
        [{"type": "text", "text": "Partial"}, {"type": "refusal", "refusal": "Can't help."}],
    ],
)
def test_empty_non_text_or_refused_generation_fails_closed(content):
    service = build_service(model=FakeRunnable(message(content)))

    assert_failed_closed(service.answer(QUESTION))


def test_safety_review_failure_fails_closed():
    service = build_service(reviewer=FakeRunnable(RuntimeError("reviewer unavailable")))

    assert_failed_closed(service.answer(QUESTION), outcome="safety_fallback")


def test_multi_query_failure_falls_back_to_the_question_alone():
    retriever = FakeRunnable([SOURCE])
    service = build_service(
        query_generator=FakeRunnable(RuntimeError("structured output failed")),
        retriever=retriever,
    )

    result = service.answer(QUESTION)

    assert result.answer == add_disclaimer(DRAFT)
    assert retriever.calls == [QUESTION]


def test_reformulation_failure_searches_with_the_original_question():
    retriever = FakeRunnable([SOURCE])
    service = build_service(
        model=FakeRunnable(RuntimeError("reformulation failed"), message("Exercise helps.")),
        retriever=retriever,
    )
    history = [HumanMessage(content="Earlier"), AIMessage(content="Reply")]

    result = service.answer(QUESTION, history)

    assert result.answer == add_disclaimer("Exercise helps.")
    assert retriever.calls[0] == QUESTION


def test_unexpected_error_fails_closed_instead_of_raising(monkeypatch):
    def broken_guard(_text):
        raise TypeError("bug in the pipeline")

    monkeypatch.setattr(rag_service, "contains_prompt_injection", broken_guard)

    assert_failed_closed(build_service().answer(QUESTION))
