"""Models shared by SafeRAG guards and wrapper orchestration."""

from typing import Any

from pydantic import BaseModel, Field


class GuardResult(BaseModel):
    """Deterministic result returned by a guard inspection."""

    allowed: bool
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
