"""FastAPI application composition root."""

from urllib.request import Request

from fastapi import FastAPI

from backend.api import auth, conversations, documents, health, query, users
from backend.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application and register its HTTP routers."""

    app_settings = settings or get_settings()
    app = FastAPI(
        title=app_settings.app_name,
        debug=app_settings.debug,
        version="0.1.0",
    )
    app.state.settings = app_settings

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)

        # TODO: Add the three headers required in every environment.
        # Use response.headers["Header-Name"] = "required value".
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        if app_settings.app_env != "local":
            # TODO: Add Strict-Transport-Security here.
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
            pass

        return response

    for router in (
        health.router,
        auth.router,
        users.router,
        conversations.router,
        documents.router,
        query.router,
    ):
        app.include_router(router, prefix="/api")

    return app


app = create_app()
