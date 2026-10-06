"""Secured RAG query API boundary."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/query", tags=["query"])


@router.post("")
async def query_placeholder() -> None:
    """Reserve the query route until SafeRAG is wired into application dependencies."""

    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Querying is not implemented")
