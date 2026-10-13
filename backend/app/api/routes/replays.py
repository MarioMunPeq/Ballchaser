"""Endpoints de consulta de replays.

Solo lectura y siempre sobre las partidas del usuario del token.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import CurrentIdentity
from app.db.session import get_session
from app.schemas.replay import ReplayDetalle, ReplayPaginado
from app.services import stats as servicio_stats
from app.services import users

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/replays",
    response_model=ReplayPaginado,
    summary="Listar tus partidas",
)
async def listar_replays(
    identity: CurrentIdentity,
    session: SessionDep,
    playlist: Annotated[str | None, Query(description="Identificador, p.ej. ranked-duels")] = None,
    result: Annotated[str | None, Query(description="win, loss o tie")] = None,
    desde: Annotated[str | None, Query(description="AAAA-MM-DD")] = None,
    hasta: Annotated[str | None, Query(description="AAAA-MM-DD")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReplayPaginado:
    """Partidas jugadas, de la mas reciente a la mas antigua."""
    user, _created = await users.get_or_create_user(session, identity)
    return await servicio_stats.listar_replays(
        session,
        user.id,
        playlist=playlist,
        resultado=servicio_stats.validar_resultado(result),
        desde=servicio_stats.parsear_fecha(desde, "desde"),
        hasta=servicio_stats.parsear_fecha(hasta, "hasta"),
        limite=limit,
        offset=offset,
    )


@router.get("/replays/{replay_id}", response_model=ReplayDetalle, summary="Detalle de una partida")
async def obtener_replay(
    replay_id: str, identity: CurrentIdentity, session: SessionDep
) -> ReplayDetalle:
    """Detalle con tus estadisticas de esa partida.

    Solo se guardan las del usuario (ADR 0004), asi que la respuesta no incluye las de
    los rivales aunque se hubieran pedido a Ballchasing.
    """
    user, _created = await users.get_or_create_user(session, identity)
    detalle = await servicio_stats.obtener_replay(session, user.id, replay_id)
    if detalle is None:
        raise AppError(
            status_code=404,
            code="replay_not_found",
            message="No tienes esa partida.",
        )
    return detalle
