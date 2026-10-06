"""User API boundary."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def users_placeholder() -> None:
    """Reserve the user route until its behavior is designed."""

    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Users are not implemented")
