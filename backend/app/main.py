"""Punto de entrada de la aplicacion FastAPI."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from app import __version__
from app.api.router import api_router
from app.core.asyncio_setup import ensure_compatible_event_loop
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging

configure_logging()
ensure_compatible_event_loop()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("app.startup", environment=settings.environment, version=__version__)
    yield
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    """Construye la instancia de FastAPI."""
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Asocia un request_id a cada peticion para poder seguirla en los logs."""
        request_id = request.headers.get("X-Request-Id") or uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-Id"] = request_id
        return response

    app.include_router(api_router)
    register_exception_handlers(app)
    return app


app = create_app()
