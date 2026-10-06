"""Authentication API boundary."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("")
async def auth_placeholder() -> None:
    """Reserve the authentication route until its behavior is designed."""

    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Authentication is not implemented")
