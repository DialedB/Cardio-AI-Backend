"""Neutral contract between backend, SafeRAG, and the future AI implementation.

Any change to these structures requires coordination between backend and AI
codeowners. This module contains data shapes only and makes no assumptions about
retrieval, prompting, generation, or other AI implementation details.
"""

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class RAGRequest(BaseModel):
    """A query accepted by a protocol-compatible RAG implementation."""

    query: str = Field(min_length=1)
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGSource(BaseModel):
    """A source reference returned with a RAG answer."""

    reference: str
    excerpt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGCriticMetadata(BaseModel):
    """Optional, implementation-neutral metadata from a future critic component."""

    accepted: bool | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGResponse(BaseModel):
    """A response returned by a protocol-compatible RAG implementation."""

    answer: str
    sources: list[RAGSource] = Field(default_factory=list)
    critic: RAGCriticMetadata | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class RAGInterface(Protocol):
    """Minimum asynchronous interface required by SafeRAG and the backend."""

    async def query(self, request: RAGRequest) -> RAGResponse:
        """Return a response for the supplied request."""

        ...
