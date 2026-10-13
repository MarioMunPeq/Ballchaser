"""Errores de aplicacion y su traduccion a respuestas HTTP."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from structlog import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Error de dominio con codigo HTTP y codigo estable para el cliente."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


def unauthorized(message: str = "Token de Firebase ausente o invalido.") -> AppError:
    """401 con la cabecera `WWW-Authenticate` que exige el esquema Bearer."""
    return AppError(
        status_code=401,
        code="unauthorized",
        message=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Engana los handlers de error de la aplicacion."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "app.error",
            code=exc.code,
            status_code=exc.status_code,
            method=request.method,
            path=request.url.path,
        )
        payload: dict[str, Any] = {"error": {"code": exc.code, "message": exc.message}}
        return JSONResponse(payload, status_code=exc.status_code, headers=exc.headers)
