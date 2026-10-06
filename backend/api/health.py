"""Service health endpoint."""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health(request: Request) -> dict[str, str]:
    """Report whether the application process can serve requests."""

    return {"status": "ok", "service": request.app.state.settings.app_name}
