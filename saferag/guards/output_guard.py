"""Output guard boundary."""

from typing import Protocol

from saferag.models import GuardResult
from shared.contracts.rag import RAGRequest, RAGResponse


class OutputGuardInterface(Protocol):
    """Interface accepted by the SafeRAG output guard boundary."""

    async def inspect(self, request: RAGRequest, response: RAGResponse) -> GuardResult:
        """Return the guard decision for a response."""

        ...


class OutputGuard:
    """Initial deterministic pass-through output guard.

    This is wiring boilerplate, not production security. Replace it with reviewed
    policies or detectors before relying on SafeRAG for output protection.
    """

    async def inspect(self, request: RAGRequest, response: RAGResponse) -> GuardResult:
        """Allow the response while the real policy is intentionally unimplemented."""

        # TODO: Apply explicitly designed and tested output security policies.
        return GuardResult(allowed=True, metadata={"guard": "pass-through"})
