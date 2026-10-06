"""SafeRAG configuration models."""

from pydantic import BaseModel


class SafeRAGConfig(BaseModel):
    """Configuration reserved for explicit, reviewed SafeRAG policy choices."""

    enabled: bool = True
