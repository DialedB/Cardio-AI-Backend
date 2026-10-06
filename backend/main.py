"""FastAPI application composition root."""

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
