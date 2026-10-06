"""Document lifecycle API boundary."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
async def documents_placeholder() -> None:
    """Reserve the document route until its behavior is designed."""

    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Documents are not implemented")
