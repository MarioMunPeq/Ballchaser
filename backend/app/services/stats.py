"""Consultas de datos: listado de replays y estadisticas agregadas.

Dos cosas que conviene tener presentes al leer el SQL:

- **Todo se filtra por `user_id`**, que viene de la identidad del token. No hay ningun
  parametro para pedir datos de otro usuario, ni siquiera por error.
- **Los nombres de columna nunca vienen del cliente.** La metrica de las tendencias se
  resuelve con un diccionario (`COLUMNAS_POR_METRICA`); interpolar el texto recibido
  en la consulta seria una inyeccion de SQL esperando a ocurrir.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.replay import PlayerStat, Replay, UserReplay
from app.schemas.replay import ReplayDetalle, ReplayPaginado, ReplayResumen
from app.schemas.stats import (
    Intervalo,
    Metrica,
    PuntoTendencia,
    ResumenStats,
    StatsPorPlaylist,
    TendenciaRespuesta,
)

# Metrica -> columna de `player_stats`. Lista cerrada a proposito.
COLUMNAS_POR_METRICA: dict[Metrica, Any] = {
    Metrica.SCORE: PlayerStat.score,
    Metrica.GOALS: PlayerStat.goals,
    Metrica.ASSISTS: PlayerStat.assists,
    Metrica.SAVES: PlayerStat.saves,
    Metrica.SHOTS: PlayerStat.shots,
    Metrica.BPM: PlayerStat.bpm,
    Metrica.AVG_AMOUNT: PlayerStat.avg_amount,
    Metrica.PERCENT_ZERO_BOOST: PlayerStat.percent_zero_boost,
    Metrica.PERCENT_FULL_BOOST: PlayerStat.percent_full_boost,
    Metrica.AVG_SPEED: PlayerStat.avg_speed,
    Metrica.PERCENT_SUPERSONIC_SPEED: PlayerStat.percent_supersonic_speed,
    Metrica.PERCENT_GROUND: PlayerStat.percent_ground,
    Metrica.PERCENT_LOW_AIR: PlayerStat.percent_low_air,
    Metrica.PERCENT_HIGH_AIR: PlayerStat.percent_high_air,
    Metrica.PERCENT_DEFENSIVE_THIRD: PlayerStat.percent_defensive_third,
    Metrica.PERCENT_OFFENSIVE_THIRD: PlayerStat.percent_offensive_third,
    Metrica.PERCENT_BEHIND_BALL: PlayerStat.percent_behind_ball,
    Metrica.PERCENT_MOST_BACK: PlayerStat.percent_most_back,
    Metrica.PERCENT_MOST_FORWARD: PlayerStat.percent_most_forward,
    Metrica.DEMOS_INFLICTED: PlayerStat.demos_inflicted,
    Metrica.DEMOS_TAKEN: PlayerStat.demos_taken,
    Metrica.EPIC_SAVES: PlayerStat.epic_saves,
    Metrica.CLEARS: PlayerStat.clears,
    Metrica.CENTERS: PlayerStat.centers,
    Metrica.AERIAL_HITS: PlayerStat.aerial_hits,
    Metrica.FIRST_TOUCHES: PlayerStat.first_touches,
    Metrica.FLIP_RESETS: PlayerStat.flip_resets,
}

LIMITE_MAXIMO_PAGINA = 200


@dataclass(frozen=True)
class FiltroPartidas:
    """Filtros del listado. No lleva `user_id`: ese siempre va, y se aplica aparte."""

    playlist: str | None = None
    resultado: str | None = None
    desde: datetime | None = None
    hasta: datetime | None = None


def _base(user_id: uuid.UUID) -> Select[Any]:
    """Punto de partida de toda consulta: las partidas del usuario."""
    return (
        select(UserReplay, Replay, PlayerStat)
        .join(Replay, Replay.ballchasing_id == UserReplay.replay_id)
        .join(PlayerStat, PlayerStat.replay_id == UserReplay.replay_id)
        .where(UserReplay.user_id == user_id)
    )


def _aplicar(sentencia: Select[Any], filtro: FiltroPartidas) -> Select[Any]:
    if filtro.playlist:
        sentencia = sentencia.where(Replay.playlist_id == filtro.playlist)
    if filtro.resultado:
        sentencia = sentencia.where(UserReplay.result == filtro.resultado)
    if filtro.desde:
        sentencia = sentencia.where(Replay.played_at >= filtro.desde)
    if filtro.hasta:
        # El filtro `hasta` es inclusivo: si el cliente manda un dia suelto ("hasta
        # 2026-05-01"), quiere ese dia entero, no solo las 00:00.
        fin = filtro.hasta
        if fin.hour == 0 and fin.minute == 0 and fin.second == 0:
            fin = fin.replace(hour=23, minute=59, second=59)
        sentencia = sentencia.where(Replay.played_at <= fin)
    return sentencia


async def listar_replays(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    playlist: str | None = None,
    resultado: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    limite: int = 50,
    offset: int = 0,
) -> ReplayPaginado:
    """Partidas del usuario, de la mas reciente a la mas antigua.

    `user_replays` ya tiene una fila por partida (unicidad `user_id + replay_id`), asi
    que no hace falta agrupar nada: se piden las partidas y sus estadisticas en dos
    consultas. La alternativa, un `GROUP BY` con las columnas de las tres tablas, es
    invalida en Postgres (solo admite dependencia funcional si se agrupa por la clave
    primaria) aunque SQLite la acepte.
    """
    filtro = FiltroPartidas(playlist=playlist, resultado=resultado, desde=desde, hasta=hasta)
    limite = max(1, min(limite, LIMITE_MAXIMO_PAGINA))
    offset = max(0, offset)

    consulta = _aplicar(
        select(UserReplay, Replay)
        .join(Replay, Replay.ballchasing_id == UserReplay.replay_id)
        .where(UserReplay.user_id == user_id),
        filtro,
    )

    total = await session.scalar(
        _aplicar(
            select(func.count())
            .select_from(UserReplay)
            .join(Replay, Replay.ballchasing_id == UserReplay.replay_id)
            .where(UserReplay.user_id == user_id),
            filtro,
        )
    )

    filas = (
        await session.execute(
            consulta.order_by(Replay.played_at.desc(), Replay.ballchasing_id)
            .limit(limite)
            .offset(offset)
        )
    ).all()

    estadisticas = await _estadisticas_de(session, [replay.ballchasing_id for _, replay in filas])

    return ReplayPaginado(
        items=[
            _a_resumen(vinculo, replay, estadisticas.get(replay.ballchasing_id))
            for vinculo, replay in filas
        ],
        total=int(total or 0),
        limit=limite,
        offset=offset,
    )


async def _estadisticas_de(session: AsyncSession, replay_ids: list[str]) -> dict[str, PlayerStat]:
    """Estadisticas de las partidas pedidas, indexadas por id de partida.

    Con varias cuentas del usuario jugando la misma partida hay varias filas; se
    guarda una sola (la de menor `platform_id`) para que el listado tenga una fila por
    partida. El detalle de una partida si devuelve todas.
    """
    if not replay_ids:
        return {}

    filas = (
        (
            await session.execute(
                select(PlayerStat)
                .where(PlayerStat.replay_id.in_(replay_ids))
                .order_by(PlayerStat.platform, PlayerStat.platform_id)
            )
        )
        .scalars()
        .all()
    )

    resultado: dict[str, PlayerStat] = {}
    for fila in filas:
        # `sorted` por plataforma deja la primera de cada partida, que es la del
        # identificador mas bajo.
        resultado.setdefault(fila.replay_id, fila)
    return resultado


async def obtener_replay(
    session: AsyncSession, user_id: uuid.UUID, replay_id: str
) -> ReplayDetalle | None:
    """Detalle de una partida del usuario, o `None` si no es suya.

    `None` en lugar de un error distinto: no se confirma si ese id existe en la base
    para otra cuenta.
    """
    filas = (await session.execute(_base(user_id).where(Replay.ballchasing_id == replay_id))).all()
    if not filas:
        return None

    vinculo, replay, stats_primera = filas[0]
    return ReplayDetalle(
        replay=_a_resumen(vinculo, replay, stats_primera),
        duration=replay.duration,
        play_duration=replay.play_duration,
        overtime=replay.overtime,
        season=replay.season,
        season_type=replay.season_type,
        team_size=replay.team_size,
        stats=[fila[2] for fila in filas if fila[2] is not None],
    )


async def resumen(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    playlist: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
) -> ResumenStats:
    """Agregados del usuario en un rango, con desglose por playlist."""
    filtro = FiltroPartidas(playlist=playlist, desde=desde, hasta=hasta)

    valores = (
        await session.execute(
            _aplicar(_base(user_id), filtro)
            .group_by(None)
            .with_only_columns(
                func.count(func.distinct(UserReplay.replay_id)).label("replays"),
                func.count(func.distinct(UserReplay.replay_id))
                .filter(UserReplay.result == "win")
                .label("wins"),
                func.count(func.distinct(UserReplay.replay_id))
                .filter(UserReplay.result == "loss")
                .label("losses"),
                func.count(func.distinct(UserReplay.replay_id))
                .filter(UserReplay.result == "tie")
                .label("ties"),
                func.coalesce(func.sum(PlayerStat.goals), 0).label("goals"),
                func.coalesce(func.sum(PlayerStat.goals_against), 0).label("goals_against"),
                func.coalesce(func.sum(PlayerStat.assists), 0).label("assists"),
                func.coalesce(func.sum(PlayerStat.saves), 0).label("saves"),
                func.coalesce(func.sum(PlayerStat.shots), 0).label("shots"),
                func.coalesce(func.sum(PlayerStat.demos_inflicted), 0).label("demos_inflict"),
                func.coalesce(func.sum(PlayerStat.demos_taken), 0).label("demos_taken"),
                func.avg(PlayerStat.score).label("avg_score"),
                func.avg(PlayerStat.bpm).label("avg_bpm"),
                func.avg(PlayerStat.percent_full_boost).label("avg_full_boost"),
                func.avg(PlayerStat.percent_zero_boost).label("avg_zero_boost"),
                func.avg(PlayerStat.percent_supersonic_speed).label("avg_supersonic"),
                func.avg(PlayerStat.percent_ground).label("avg_ground"),
                func.avg(Replay.duration).label("avg_duration"),
            )
        )
    ).one()

    decisas = int(valores.replays or 0)
    victorias = int(valores.wins or 0)
    derrotas = int(valores.losses or 0)
    # El porcentaje se calcula sobre las partidas con resultado claro: contar un
    # empate como derrota bajaria una metrica que no fue tal.
    con_resultado = victorias + derrotas

    return ResumenStats(
        replays=decisas,
        wins=victorias,
        losses=derrotas,
        ties=int(valores.ties or 0),
        win_rate=round(victorias / con_resultado * 100, 2) if con_resultado else None,
        goals=int(valores.goals or 0),
        goals_against=int(valores.goals_against or 0),
        assists=int(valores.assists or 0),
        saves=int(valores.saves or 0),
        shots=int(valores.shots or 0),
        demos_inflicted=int(valores.demos_inflict or 0),
        demos_taken=int(valores.demos_taken or 0),
        avg_score=_redondear(valores.avg_score),
        avg_bpm=_redondear(valores.avg_bpm),
        avg_percent_full_boost=_redondear(valores.avg_full_boost),
        avg_percent_zero_boost=_redondear(valores.avg_zero_boost),
        avg_percent_supersonic_speed=_redondear(valores.avg_supersonic),
        avg_percent_ground=_redondear(valores.avg_ground),
        avg_duration=_redondear(valores.avg_duration),
        por_playlist=await _por_playlist(session, user_id, filtro),
    )


async def _por_playlist(
    session: AsyncSession, user_id: uuid.UUID, filtro: FiltroPartidas
) -> list[StatsPorPlaylist]:
    """Desglose por playlist: de donde sale la decision de donde practicar."""
    consulta = (
        _aplicar(_base(user_id), filtro)
        .with_only_columns(
            Replay.playlist_id,
            func.max(Replay.playlist_name).label("playlist_name"),
            func.count(func.distinct(UserReplay.replay_id)).label("replays"),
            func.count(func.distinct(UserReplay.replay_id))
            .filter(UserReplay.result == "win")
            .label("wins"),
            func.avg(PlayerStat.score).label("avg_score"),
            func.avg(PlayerStat.bpm).label("avg_bpm"),
        )
        .group_by(Replay.playlist_id)
    )

    filas = (await session.execute(consulta)).all()
    resultado = [
        StatsPorPlaylist(
            playlist_id=playlist_id,
            playlist_name=nombre,
            replays=int(replays or 0),
            wins=int(wins or 0),
            win_rate=round(int(wins or 0) / int(replays or 1) * 100, 2) if replays else None,
            avg_score=_redondear(avg_score),
            avg_bpm=_redondear(avg_bpm),
        )
        for playlist_id, nombre, replays, wins, avg_score, avg_bpm in filas
    ]
    resultado.sort(key=lambda p: p.replays, reverse=True)
    return resultado


async def tendencias(
    session: AsyncSession,
    user_id: uuid.UUID,
    metrica: Metrica,
    *,
    intervalo: Intervalo = Intervalo.SEMANA,
    playlist: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
) -> TendenciaRespuesta:
    """Serie temporal de una metrica, agrupada por periodo.

    Los periodos sin datos se omiten en lugar de rellenarse con ceros: poner un 0 donde
    no se jugó hace que cualquier grafica parezca una caida de rendimiento.
    """
    columna = COLUMNAS_POR_METRICA[metrica]
    filtro = FiltroPartidas(playlist=playlist, desde=desde, hasta=hasta)
    periodo = _expresion_periodo(session, Replay.played_at, intervalo)

    consulta = (
        _aplicar(_base(user_id), filtro)
        .with_only_columns(
            periodo.label("periodo"),
            func.avg(columna).label("valor"),
            func.sum(columna).label("total"),
            func.count(func.distinct(UserReplay.replay_id)).label("replays"),
        )
        .group_by(periodo)
        .order_by(periodo)
    )

    filas = (await session.execute(consulta)).all()
    return TendenciaRespuesta(
        metrica=metrica,
        intervalo=intervalo,
        puntos=[
            PuntoTendencia(
                periodo=_a_fecha(periodo),
                valor=_redondear(valor),
                total=_redondear(total),
                replays=int(replays or 0),
            )
            for periodo, valor, total, replays in filas
        ],
    )


# --- ayudas de dialecto y de formato ---


def _expresion_periodo(session: AsyncSession, columna: Any, intervalo: Intervalo) -> Any:
    """Expresion que trunca una fecha al inicio de su periodo.

    Postgres tiene `date_trunc`; SQLite no, asi que se recurre a `strftime`. En
    produccion siempre es Postgres: el camino de SQLite existe para que los tests
    corran sin levantar una base de datos.
    """
    if session.get_bind().dialect.name == "postgresql":
        return func.date_trunc(intervalo.value, columna)

    formato = {"day": "%Y-%m-%d", "week": "%Y-%m-%d", "month": "%Y-%m-01"}[intervalo.value]
    return func.strftime(formato, columna)


def _a_fecha(valor: Any) -> date:
    """Normaliza a `date`: Postgres devuelve un timestamp y SQLite un texto."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def _redondear(valor: Any) -> float | None:
    return None if valor is None else round(float(valor), 2)


def _a_resumen(user_replay: UserReplay, replay: Replay, stats: PlayerStat | None) -> ReplayResumen:
    return ReplayResumen(
        id=replay.ballchasing_id,
        played_at=replay.played_at,
        playlist_id=replay.playlist_id,
        playlist_name=replay.playlist_name,
        map_code=replay.map_code,
        map_name=replay.map_name,
        blue_goals=replay.blue_goals,
        orange_goals=replay.orange_goals,
        team=user_replay.team,
        result=user_replay.result,
        score=stats.score if stats else None,
        goals=stats.goals if stats else None,
        assists=stats.assists if stats else None,
        saves=stats.saves if stats else None,
        bpm=stats.bpm if stats else None,
        centers=stats.centers if stats else None,
    )


def parsear_fecha(valor: str | None, nombre: str) -> datetime | None:
    """Convierte `AAAA-MM-DD` (o con hora) en datetime para filtrar."""
    if valor is None:
        return None
    try:
        fecha = datetime.fromisoformat(valor)
    except ValueError as exc:
        raise AppError(
            status_code=422,
            code="invalid_date",
            message=f"{nombre} no es una fecha valida (usa AAAA-MM-DD).",
        ) from exc
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=UTC)


def validar_resultado(valor: str | None) -> str | None:
    if valor is None:
        return None
    normalizado = valor.lower()
    if normalizado not in {"win", "loss", "tie"}:
        raise AppError(
            status_code=422, code="invalid_result", message="result debe ser win, loss o tie."
        )
    return normalizado
