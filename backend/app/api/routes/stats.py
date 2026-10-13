"""Endpoints de estadisticas agregadas.

Respuestas pensadas para las graficas del panel: un resumen con medias, el desglose
por playlist y la serie temporal de una metrica.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentIdentity
from app.db.session import get_session
from app.schemas.stats import (
    Intervalo,
    Metrica,
    ResumenStats,
    TendenciaRespuesta,
)
from app.services import stats as servicio_stats
from app.services import users

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/stats/summary", response_model=ResumenStats, summary="Resumen global")
async def resumen(
    identity: CurrentIdentity,
    session: SessionDep,
    playlist: Annotated[str | None, Query()] = None,
    desde: Annotated[str | None, Query(description="AAAA-MM-DD")] = None,
    hasta: Annotated[str | None, Query(description="AAAA-MM-DD")] = None,
) -> ResumenStats:
    """Victorias, goles, paradas y medias, con el desglose por playlist."""
    user, _created = await users.get_or_create_user(session, identity)
    return await servicio_stats.resumen(
        session,
        user.id,
        playlist=playlist,
        desde=servicio_stats.parsear_fecha(desde, "desde"),
        hasta=servicio_stats.parsear_fecha(hasta, "hasta"),
    )


@router.get("/stats/trends", response_model=TendenciaRespuesta, summary="Serie temporal")
async def tendencias(
    identity: CurrentIdentity,
    session: SessionDep,
    metric: Metrica = Query(description="Metrica a seguir en el tiempo."),
    interval: Annotated[Intervalo, Query(description="day, week o month")] = Intervalo.SEMANA,
    playlist: Annotated[str | None, Query()] = None,
    desde: Annotated[str | None, Query(description="AAAA-MM-DD")] = None,
    hasta: Annotated[str | None, Query(description="AAAA-MM-DD")] = None,
) -> TendenciaRespuesta:
    """Media de una metrica por periodo.

    `metric` y `interval` son listas cerradas: un valor desconocido da 422 en lugar de
    acabar en la consulta como texto.
    """
    user, _created = await users.get_or_create_user(session, identity)
    return await servicio_stats.tendencias(
        session,
        user.id,
        metric,
        intervalo=interval,
        playlist=playlist,
        desde=servicio_stats.parsear_fecha(desde, "desde"),
        hasta=servicio_stats.parsear_fecha(hasta, "hasta"),
    )
