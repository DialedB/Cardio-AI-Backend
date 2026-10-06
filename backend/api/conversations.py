"""Conversation API boundary."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
async def conversations_placeholder() -> None:
    """Reserve the conversation route until its behavior is designed."""

    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Conversations are not implemented")
