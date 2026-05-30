"""FastAPI app factory for blackheart-ingest HTTP endpoints."""

from __future__ import annotations

from fastapi import FastAPI

from .api.compute import router as compute_router
from .shared.logging_setup import configure as configure_logging
from .shared.settings import get_settings


def create_app(settings=None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Optional Settings instance. If None, uses get_settings().
    """
    settings = settings or get_settings()
    configure_logging()

    app = FastAPI(
        title="Blackheart ingest server",
        version="0.1.0",
        description="Feature computation and streaming endpoints.",
    )

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    app.include_router(compute_router)

    return app


# Module-level app for uvicorn invocations
app = create_app()
