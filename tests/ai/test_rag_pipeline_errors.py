"""Fail-closed behavior of RAG_Pipeline.ask_question when a pipeline step fails.

RAG_Pipeline builds its clients and checks the Neon schema at import time, so the
fixture imports it with the Neon pieces stubbed and fake credentials. No network
calls are made: every model, retriever, and safety call is replaced per test.
"""

import importlib
import sys
from types import SimpleNamespace

import full_text_schema
import langchain_postgres
import pytest
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever


class EmptyRetriever(BaseRetriever):
    def _get_relevant_documents(self, query, *, run_manager):
        return []


class FakeVectorStore:
    def __init__(self, **_kwargs):
        pass

    def as_retriever(self, **_kwargs):
        return EmptyRetriever()


class FakeRunnable:
    """Returns (or raises) the given outcomes in order and records its inputs."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def invoke(self, value, *_args, **_kwargs):
        self.calls.append(value)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def message(text):
    return SimpleNamespace(content=text)


SOURCE = Document(page_content="Regular exercise supports heart health.", metadata={})


@pytest.fixture
def rag(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost:5432/test")
    monkeypatch.setattr(full_text_schema, "require_full_text_search_schema", lambda: None)
    monkeypatch.setattr(langchain_postgres, "PGVector", FakeVectorStore)
    sys.modules.pop("RAG_Pipeline", None)
    module = importlib.import_module("RAG_Pipeline")

    monkeypatch.setattr(module, "moderate_text", lambda _text: False)
    monkeypatch.setattr(
        module, "safe_response", lambda _question, answer, _context: module.add_disclaimer(answer)
    )
    monkeypatch.setattr(module, "model", FakeRunnable(message("Exercise helps the heart.")))
    monkeypatch.setattr(
        module, "model_with_tools", FakeRunnable(SimpleNamespace(queries=["variation"]))
    )
    monkeypatch.setattr(module, "retriever", FakeRunnable([SOURCE]))
    yield module
    sys.modules.pop("RAG_Pipeline", None)


QUESTION = "How does exercise affect heart health?"


def test_successful_question_is_answered_and_recorded(rag):
    answer = rag.ask_question(QUESTION)

    assert answer == rag.add_disclaimer("Exercise helps the heart.")
    assert len(rag.chat_history) == 2


def test_retrieval_failure_fails_closed_without_recording_history(rag):
    rag.retriever = FakeRunnable(ConnectionError("Neon unavailable"))

    answer = rag.ask_question(QUESTION)

    assert answer == rag.add_disclaimer(rag.CHECK_UNAVAILABLE)
    assert rag.chat_history == []


def test_generation_failure_fails_closed(rag):
    rag.model = FakeRunnable(TimeoutError("request timed out"))

    assert rag.ask_question(QUESTION) == rag.add_disclaimer(rag.CHECK_UNAVAILABLE)
    assert rag.chat_history == []


def test_text_blocks_are_joined_into_the_answer(rag):
    rag.model = FakeRunnable(
        message(
            [
                {"type": "reasoning", "reasoning": "internal"},
                {"type": "text", "text": "Exercise helps "},
                "the heart.",
                {"type": "text", "text": None},
            ]
        )
    )

    assert rag.ask_question(QUESTION) == rag.add_disclaimer("Exercise helps the heart.")
    assert len(rag.chat_history) == 2


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
def test_empty_non_text_or_refused_generation_fails_closed(rag, content):
    rag.model = FakeRunnable(message(content))

    assert rag.ask_question(QUESTION) == rag.add_disclaimer(rag.CHECK_UNAVAILABLE)
    assert rag.chat_history == []


def test_safety_review_failure_fails_closed_without_recording_history(rag):
    def unavailable_review(*_args):
        raise RuntimeError("reviewer unavailable")

    rag.safe_response = unavailable_review

    assert rag.ask_question(QUESTION) == rag.add_disclaimer(rag.CHECK_UNAVAILABLE)
    assert rag.chat_history == []


def test_multi_query_failure_falls_back_to_the_question_alone(rag):
    rag.model_with_tools = FakeRunnable(RuntimeError("structured output failed"))

    answer = rag.ask_question(QUESTION)

    assert answer == rag.add_disclaimer("Exercise helps the heart.")
    assert rag.retriever.calls == [QUESTION]


def test_reformulation_failure_searches_with_the_original_question(rag):
    rag.chat_history.extend([rag.HumanMessage(content="Earlier"), rag.AIMessage(content="Reply")])
    rag.model = FakeRunnable(RuntimeError("reformulation failed"), message("Exercise helps."))

    answer = rag.ask_question(QUESTION)

    assert answer == rag.add_disclaimer("Exercise helps.")
    assert rag.retriever.calls[0] == QUESTION


def test_chat_loop_survives_unexpected_errors_and_exits_on_eof(rag, monkeypatch, capsys):
    inputs = iter([QUESTION])

    def fake_input(_prompt):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError from None

    def broken_ask(_question):
        raise RuntimeError("unexpected")

    monkeypatch.setattr("builtins.input", fake_input)
    rag.ask_question = broken_ask

    rag.start_chat()

    output = capsys.readouterr().out
    assert rag.CHECK_UNAVAILABLE in output
    assert "Goodbye!" in output


def test_openai_clients_use_configured_timeout_and_retries(rag):
    for client in (rag.review_model, rag.embedding_model):
        assert client.request_timeout == rag.OPENAI_TIMEOUT_SECONDS
        assert client.max_retries == rag.OPENAI_MAX_RETRIES
    assert rag.moderation_client.timeout == rag.OPENAI_TIMEOUT_SECONDS
    assert rag.moderation_client.max_retries == rag.OPENAI_MAX_RETRIES
