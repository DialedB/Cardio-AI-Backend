"""The backend's single doorway into the secured RAG subsystem.

The object supplied to this adapter is expected to be SafeRAG in production. Keeping
the dependency protocol-based prevents backend business logic from depending on AI
implementation details.
"""

from shared.contracts.rag import RAGInterface, RAGRequest, RAGResponse


class RAGClient:
    """Thin adapter around a runtime-provided, protocol-compatible secured RAG."""

    def __init__(self, secured_rag: RAGInterface) -> None:
        self._secured_rag = secured_rag

    async def query(self, request: RAGRequest) -> RAGResponse:
        """Forward a query through the configured secured RAG boundary."""

        return await self._secured_rag.query(request)
