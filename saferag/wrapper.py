"""SafeRAG decorator orchestration."""

from saferag.guards.input_guard import InputGuard, InputGuardInterface
from saferag.guards.output_guard import OutputGuard, OutputGuardInterface
from shared.contracts.rag import RAGInterface, RAGRequest, RAGResponse


class SafeRAGError(RuntimeError):
    """Base error raised when a SafeRAG guard blocks processing."""


class InputBlockedError(SafeRAGError):
    """Raised before RAG invocation when the input guard blocks a request."""


class OutputBlockedError(SafeRAGError):
    """Raised instead of returning a response blocked by the output guard."""


class SafeRAG:
    """Wrap a RAG implementation with ordered input and output guard checks."""

    def __init__(
        self,
        rag: RAGInterface,
        *,
        input_guard: InputGuardInterface | None = None,
        output_guard: OutputGuardInterface | None = None,
    ) -> None:
        self._rag = rag
        self._input_guard = input_guard or InputGuard()
        self._output_guard = output_guard or OutputGuard()

    async def query(self, request: RAGRequest) -> RAGResponse:
        """Inspect input, invoke the wrapped RAG, then inspect its output."""

        input_result = await self._input_guard.inspect(request)
        if not input_result.allowed:
            raise InputBlockedError(input_result.reason or "Input blocked by SafeRAG")

        response = await self._rag.query(request)

        output_result = await self._output_guard.inspect(request, response)
        if not output_result.allowed:
            raise OutputBlockedError(output_result.reason or "Output blocked by SafeRAG")

        return response
