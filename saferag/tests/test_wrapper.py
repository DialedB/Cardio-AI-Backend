"""Behavioral tests for SafeRAG's decorator ordering and blocking semantics."""

import pytest

from saferag.models import GuardResult
from saferag.wrapper import InputBlockedError, OutputBlockedError, SafeRAG
from shared.contracts.rag import RAGRequest, RAGResponse


class RecordingRAG:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.called = False

    async def query(self, request: RAGRequest) -> RAGResponse:
        self.called = True
        self.events.append("rag")
        return RAGResponse(answer=f"answer to {request.query}")


class RecordingInputGuard:
    def __init__(self, events: list[str], *, allowed: bool = True) -> None:
        self.events = events
        self.allowed = allowed

    async def inspect(self, request: RAGRequest) -> GuardResult:
        self.events.append("input")
        return GuardResult(allowed=self.allowed, reason="test input decision")


class RecordingOutputGuard:
    def __init__(self, events: list[str], *, allowed: bool = True) -> None:
        self.events = events
        self.allowed = allowed

    async def inspect(self, request: RAGRequest, response: RAGResponse) -> GuardResult:
        self.events.append("output")
        return GuardResult(allowed=self.allowed, reason="test output decision")


@pytest.mark.asyncio
async def test_wrapper_returns_approved_response() -> None:
    events: list[str] = []
    safe_rag = SafeRAG(RecordingRAG(events))

    response = await safe_rag.query(RAGRequest(query="What is CardioSmart?"))

    assert response.answer == "answer to What is CardioSmart?"
    assert events == ["rag"]


@pytest.mark.asyncio
async def test_input_guard_runs_before_rag() -> None:
    events: list[str] = []
    safe_rag = SafeRAG(
        RecordingRAG(events),
        input_guard=RecordingInputGuard(events),
        output_guard=RecordingOutputGuard(events),
    )

    await safe_rag.query(RAGRequest(query="ordered input"))

    assert events.index("input") < events.index("rag")


@pytest.mark.asyncio
async def test_output_guard_runs_after_rag() -> None:
    events: list[str] = []
    safe_rag = SafeRAG(
        RecordingRAG(events),
        input_guard=RecordingInputGuard(events),
        output_guard=RecordingOutputGuard(events),
    )

    await safe_rag.query(RAGRequest(query="ordered output"))

    assert events.index("rag") < events.index("output")
    assert events == ["input", "rag", "output"]


@pytest.mark.asyncio
async def test_blocked_input_does_not_invoke_rag() -> None:
    events: list[str] = []
    rag = RecordingRAG(events)
    safe_rag = SafeRAG(
        rag,
        input_guard=RecordingInputGuard(events, allowed=False),
        output_guard=RecordingOutputGuard(events),
    )

    with pytest.raises(InputBlockedError, match="test input decision"):
        await safe_rag.query(RAGRequest(query="blocked"))

    assert rag.called is False
    assert events == ["input"]


@pytest.mark.asyncio
async def test_blocked_output_is_not_returned_as_approved() -> None:
    events: list[str] = []
    safe_rag = SafeRAG(
        RecordingRAG(events),
        input_guard=RecordingInputGuard(events),
        output_guard=RecordingOutputGuard(events, allowed=False),
    )

    with pytest.raises(OutputBlockedError, match="test output decision"):
        await safe_rag.query(RAGRequest(query="unsafe response"))

    assert events == ["input", "rag", "output"]
