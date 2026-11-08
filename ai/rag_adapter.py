"""Adapts RagService to the shared RAGInterface used by SafeRAG and the backend.

Kept apart from rag_service.py because it imports ``shared``, which the standalone
CLI environment (ai/requirements.txt) does not install.
"""

import asyncio
from pathlib import PureWindowsPath

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from rag_service import RagService

from shared.contracts.rag import RAGCriticMetadata, RAGRequest, RAGResponse, RAGSource

HISTORY_METADATA_KEY = "history"
MESSAGE_TYPES = {"user": HumanMessage, "assistant": AIMessage}


def parse_history(raw_history) -> list[BaseMessage]:
    """Convert ``[{"role": "user"|"assistant", "content": str}, ...]`` to chat messages.

    Malformed history is a caller bug, so it raises rather than silently dropping
    context. Error messages never quote the content.
    """
    if raw_history is None:
        return []
    if not isinstance(raw_history, list):
        raise ValueError(f"metadata[{HISTORY_METADATA_KEY!r}] must be a list of messages")

    messages = []
    for index, entry in enumerate(raw_history):
        role = entry.get("role") if isinstance(entry, dict) else None
        content = entry.get("content") if isinstance(entry, dict) else None
        if role not in MESSAGE_TYPES or not isinstance(content, str):
            raise ValueError(
                f"metadata[{HISTORY_METADATA_KEY!r}][{index}] must have a role of "
                '"user" or "assistant" and string content'
            )
        messages.append(MESSAGE_TYPES[role](content=content))
    return messages


def to_rag_source(doc: Document) -> RAGSource:
    """Map a chunk to a contract source, without exposing the absolute ingestion path."""
    source_path = doc.metadata.get("source")
    # PureWindowsPath splits on both separators, so paths ingested on any OS work.
    file_name = PureWindowsPath(source_path).name if isinstance(source_path, str) else None
    page = doc.metadata.get("page")
    return RAGSource(
        reference=doc.metadata.get("source_key") or file_name or "unknown",
        excerpt=doc.page_content,
        metadata={} if page is None else {"page": page},
    )


class RagAdapter:
    """Implements ``RAGInterface`` on top of a RagService."""

    def __init__(self, service: RagService) -> None:
        self._service = service

    async def query(self, request: RAGRequest) -> RAGResponse:
        """Answer a request. The pipeline's clients are sync, so it runs in a worker thread."""
        history = parse_history(request.metadata.get(HISTORY_METADATA_KEY))
        result = await asyncio.to_thread(self._service.answer, request.query, history)

        critic = None
        if result.review_approved is not None:
            critic = RAGCriticMetadata(accepted=result.review_approved)
        # Refusals and failures don't return excerpts that didn't back a shown answer.
        sources = result.sources if result.outcome == "answered" else ()
        return RAGResponse(
            answer=result.answer,
            sources=[to_rag_source(doc) for doc in sources],
            critic=critic,
            metadata={
                "outcome": result.outcome,
                "record_in_history": result.record_in_history,
            },
        )
