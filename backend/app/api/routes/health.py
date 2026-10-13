"""Endpoints de operacion."""

from fastapi import APIRouter, Response, status

from app import __version__

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK, summary="Comprobacion de vida")
async def health() -> dict[str, str]:
    """Endpoint publico que devuelve 200 mientras el proceso responda."""
    return {"status": "ok", "version": __version__}


@router.head("/health", include_in_schema=False)
async def health_head() -> Response:
    """Variante HEAD para probes que no esperan cuerpo."""
    return Response(status_code=status.HTTP_200_OK)
