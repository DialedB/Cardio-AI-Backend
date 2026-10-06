"""Input guard boundary."""

from typing import Protocol

from saferag.models import GuardResult
from shared.contracts.rag import RAGRequest


class InputGuardInterface(Protocol):
    """Interface accepted by the SafeRAG input guard boundary."""

    async def inspect(self, request: RAGRequest) -> GuardResult:
        """Return the guard decision for a request."""

        ...


class InputGuard:
    """Initial deterministic pass-through input guard.

    This is wiring boilerplate, not production security. Replace it with reviewed
    policies or detectors before relying on SafeRAG for input protection.
    """

    async def inspect(self, request: RAGRequest) -> GuardResult:
        """Allow the request while the real policy is intentionally unimplemented."""

        # TODO: Apply explicitly designed and tested input security policies.
        return GuardResult(allowed=True, metadata={"guard": "pass-through"})
