import defusedxml.ElementTree as DefusedET
import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(tags=["steam"])


class ResolveVanityResponse(BaseModel):
    steam_id: str
    vanity: str
    community_visibility_state: int | None = None
    profile_state: int | None = None


@router.get("/resolve-vanity")
async def resolve_vanity(
    vanity: str = Query(..., description="Nombre vanity de Steam (ej: Snakeyesmp)"),
) -> ResolveVanityResponse:
    """
    Resuelve un nombre vanity de Steam a su SteamID64 (17 dígitos).

    Usa el endpoint público de Steam que devuelve XML:
    https://steamcommunity.com/id/{vanity}/?xml=1

    No requiere API key de Steam.
    """
    vanity_limpio = vanity.strip()
    if not vanity_limpio:
        raise HTTPException(status_code=422, detail="El nombre vanity es obligatorio")

    url = f"https://steamcommunity.com/id/{vanity_limpio}/?xml=1"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url, headers={"Accept": "application/xml"})
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=502, detail=f"No se pudo conectar con Steam: {e}"
            ) from e

    if resp.status_code == 404:
        raise HTTPException(
            status_code=404, detail=f"No existe un perfil de Steam con el nombre '{vanity_limpio}'"
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Steam respondió con error {resp.status_code}")

    # Parsear XML de forma segura
    try:
        root = DefusedET.fromstring(resp.text)
        steam_id = root.findtext(".//steamID64")
        if not steam_id:
            raise HTTPException(
                status_code=404, detail=f"No se encontró steamID64 para '{vanity_limpio}'"
            )
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Error parseando respuesta de Steam: {e}"
        ) from e

    return ResolveVanityResponse(
        steam_id=steam_id,
        vanity=vanity_limpio,
    )
