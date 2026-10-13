"""Ingesta de replays de Ballchasing.

Como funciona, según lo comprobado en `docs/ballchasing-api.md`:

- Se listan las partidas del usuario filtrando por `player-id` (sus cuentas de juego),
  no por `uploader=me`: asi aparecen tambien las que subio otra persona.
- Para cada partida que no este ya guardada se pide el detalle, se comprueba que este
  en estado `ok` y se inserta en su propia transaccion.
- Si una partida falla, se cuenta y se sigue: una partida rara no puede tirar el lote.

Idempotencia: la clave primaria es `replays.ballchasing_id`. Una partida ya ingerida se
descarta antes de pedir siquiera su detalle, asi que el worker puede morir y repetirse
sin duplicar nada ni gastar cuota.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.game_account import GameAccount
from app.db.models.replay import PlayerStat, Replay, UserReplay
from app.db.upsert import insertar_si_no_existe
from app.services.ballchasing import ClienteBallchasing, id_de_plataforma

logger = structlog.get_logger(__name__)

# Cuantas paginas seguidas sin nada nuevo cortan el recorrido. El listado viene de mas
# reciente a mas antiguo, asi que en cuanto una pagina entera ya esta guardada, lo que
# queda es mas viejo. Dos paginas de margen evitan cortar de mas si el orden no fuera
# estricto.
PAGINAS_SIN_NUEVOS_PARA_PARAR = 2
PAGINAS_MAXIMAS = 200
EQUIPOS = ("blue", "orange")


@dataclass
class ResumenIngesta:
    """Resultado de una sincronizacion."""

    nuevos: int = 0
    omitidos: int = 0
    fallidos: int = 0
    paginas: int = 0
    ultima_partida: datetime | None = None
    player_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class JugadorIdentificado:
    """Un jugador del replay que corresponde a una de las cuentas del usuario."""

    platform: str
    platform_id: str
    team: str
    game_account_id: uuid.UUID
    mvp: bool | None
    name: str | None
    stats: dict[str, Any]


def _clave(platform: str, platform_id: object) -> tuple[str, str]:
    return (str(platform).lower(), str(platform_id).strip())


def parsear_fecha(texto: str) -> datetime:
    """Convierte el RFC3339 de Ballchasing (`...Z`) en datetime con zona horaria."""
    fecha = datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=UTC)


def aplanar_stats(jugador: dict[str, Any]) -> dict[str, Any]:
    """Aplana `stats.{core,boost,movement,positioning,demo}` a columnas.

    La API agrupa las metricas y la tabla las tiene en columnas planas, para poder
    agregar en SQL sin rodeos. Las que solo existen en replays recientes salen en `None`
    cuando no vienen.
    """
    stats = jugador.get("stats") or {}
    core = stats.get("core") or {}
    boost = stats.get("boost") or {}
    movimiento = stats.get("movement") or {}
    posicionamiento = stats.get("positioning") or {}
    demos = stats.get("demo") or {}

    return {
        "score": core.get("score"),
        "goals": core.get("goals"),
        "assists": core.get("assists"),
        "saves": core.get("saves"),
        "shots": core.get("shots"),
        "goals_against": core.get("goals_against"),
        "shots_against": core.get("shots_against"),
        "shooting_percentage": core.get("shooting_percentage"),
        "bpm": boost.get("bpm"),
        "avg_amount": boost.get("avg_amount"),
        "percent_zero_boost": boost.get("percent_zero_boost"),
        "percent_full_boost": boost.get("percent_full_boost"),
        "amount_stolen": boost.get("amount_stolen"),
        "avg_speed": movimiento.get("avg_speed"),
        "percent_supersonic_speed": movimiento.get("percent_supersonic_speed"),
        "percent_ground": movimiento.get("percent_ground"),
        "percent_low_air": movimiento.get("percent_low_air"),
        "percent_high_air": movimiento.get("percent_high_air"),
        "percent_defensive_third": posicionamiento.get("percent_defensive_third"),
        "percent_offensive_third": posicionamiento.get("percent_offensive_third"),
        "percent_behind_ball": posicionamiento.get("percent_behind_ball"),
        "percent_most_back": posicionamiento.get("percent_most_back"),
        "percent_most_forward": posicionamiento.get("percent_most_forward"),
        "demos_inflicted": demos.get("inflicted"),
        "demos_taken": demos.get("taken"),
        # Solo en replays recientes: pueden no venir.
        "epic_saves": core.get("epic_saves"),
        "clears": core.get("clears"),
        "centers": core.get("centers"),
        "aerial_hits": core.get("aerial_hits"),
        "first_touches": core.get("first_touches"),
        "flip_resets": core.get("flip_resets"),
        "demos_inflicted_def_half": demos.get("inflicted_in_defensive_half"),
        "demos_inflicted_off_half": demos.get("inflicted_in_offensive_half"),
    }


def analizar_detalle(
    detalle: dict[str, Any], cuentas: list[GameAccount]
) -> tuple[Replay, list[JugadorIdentificado]]:
    """Convierte la respuesta de Ballchasing en filas de la base.

    Se queda solo con los jugadores que coinciden con una cuenta del usuario.
    """
    mis_cuentas = {_clave(c.platform, c.platform_id): c for c in cuentas}

    jugadores: list[JugadorIdentificado] = []
    for color in EQUIPOS:
        for jugador in (detalle.get(color) or {}).get("players") or []:
            identificador = jugador.get("id") or {}
            clave = _clave(identificador.get("platform", ""), identificador.get("id", ""))
            cuenta = mis_cuentas.get(clave)
            if cuenta is None:
                continue
            jugadores.append(
                JugadorIdentificado(
                    platform=clave[0],
                    platform_id=clave[1],
                    team=color,
                    game_account_id=cuenta.id,
                    # `mvp` solo viene en el jugador MVP: en el resto la clave no existe.
                    mvp=jugador.get("mvp"),
                    name=jugador.get("name"),
                    stats=aplanar_stats(jugador),
                )
            )

    goles = {
        color: int(((detalle.get(color) or {}).get("stats") or {}).get("core", {}).get("goals", 0))
        for color in EQUIPOS
    }

    replay = Replay(
        ballchasing_id=str(detalle["id"]),
        played_at=parsear_fecha(detalle["date"]),
        rocket_league_id=detalle.get("rocket_league_id"),
        playlist_id=detalle["playlist_id"],
        playlist_name=detalle.get("playlist_name"),
        map_code=detalle.get("map_code"),
        map_name=detalle.get("map_name"),
        team_size=detalle.get("team_size"),
        duration=detalle.get("duration"),
        play_duration=detalle.get("play_duration"),
        overtime=detalle.get("overtime"),
        season=detalle.get("season"),
        season_type=detalle.get("season_type"),
        blue_goals=goles["blue"],
        orange_goals=goles["orange"],
    )
    return replay, jugadores


def calcular_resultado(team: str, goles_blue: int, goles_orange: int) -> str:
    """`win`, `loss` o `tie`.

    Con goles iguales la partida fue a prorroga o acabo empatada. Ballchasing no publica
    el resultado de los penaltis, asi que se registra como empate en vez de inventar un
    ganador.
    """
    propias, rivales = (goles_blue, goles_orange) if team == "blue" else (goles_orange, goles_blue)
    if propias > rivales:
        return "win"
    if propias < rivales:
        return "loss"
    return "tie"


async def ya_ingerido(session: AsyncSession, replay_id: str) -> bool:
    return (
        await session.scalar(
            select(Replay.ballchasing_id).where(Replay.ballchasing_id == replay_id)
        )
        is not None
    )


async def sincronizar(
    session: AsyncSession,
    cliente: ClienteBallchasing,
    cuentas: list[GameAccount],
    user_id: uuid.UUID,
) -> ResumenIngesta:
    """Recorre el listado e ingerta las partidas nuevas del usuario."""
    resumen = ResumenIngesta()
    if not cuentas:
        logger.info("sync.sin_cuentas", user_id=str(user_id))
        return resumen

    identificadores = [id_de_plataforma(c.platform, c.platform_id) for c in cuentas]
    resumen.player_ids = identificadores

    pagina: dict[str, Any] | None = await cliente.listar_replays(
        limit=200, player_ids=identificadores
    )
    paginas_sin_nuevos = 0

    while pagina is not None and resumen.paginas < PAGINAS_MAXIMAS:
        resumen.paginas += 1
        nuevos_en_pagina = 0

        for entrada in pagina.get("list") or []:
            replay_id = str(entrada["id"])
            if await ya_ingerido(session, replay_id):
                resumen.omitidos += 1
                continue
            if await _ingerir_uno(session, cliente, replay_id, cuentas, user_id, resumen):
                nuevos_en_pagina += 1

        paginas_sin_nuevos = 0 if nuevos_en_pagina else paginas_sin_nuevos + 1
        if paginas_sin_nuevos >= PAGINAS_SIN_NUEVOS_PARA_PARAR:
            logger.info("sync.recorrido_completo", user_id=str(user_id), paginas=resumen.paginas)
            break

        # El enlace `next` se sigue literal: anadirle parametros hace que la API
        # ignore el cursor y devuelva la primera pagina otra vez.
        siguiente = pagina.get("next")
        pagina = await cliente.listar_replays(siguiente=siguiente) if siguiente else None

    logger.info(
        "sync.completada",
        user_id=str(user_id),
        nuevos=resumen.nuevos,
        omitidos=resumen.omitidos,
        fallidos=resumen.fallidos,
        paginas=resumen.paginas,
    )
    return resumen


async def _ingerir_uno(
    session: AsyncSession,
    cliente: ClienteBallchasing,
    replay_id: str,
    cuentas: list[GameAccount],
    user_id: uuid.UUID,
    resumen: ResumenIngesta,
) -> bool:
    """Ingesta una partida en su propia transaccion.

    Devuelve `True` si se guardo. Los errores se cuentan y se saltan: una partida
    imposible no puede tumbar la sincronizacion entera.
    """
    try:
        detalle = await cliente.obtener_replay(replay_id)
    except Exception:
        resumen.fallidos += 1
        logger.warning("sync.detalle_fallido", replay_id=replay_id, exc_info=True)
        return False

    estado = detalle.get("status")
    if estado != "ok":
        # `pending` o `failed`: sin estadisticas todavía. No se guarda nada, asi que
        # la proxima sincronizacion volvera a mirarla.
        resumen.omitidos += 1
        logger.info("sync.replay_no_listo", replay_id=replay_id, status=estado)
        return False

    replay, jugadores = analizar_detalle(detalle, cuentas)
    if not jugadores:
        # El listado promisea al usuario pero el detalle no lo tiene: se descarta sin
        # marcar como fallido, porque no es un error nuestro.
        resumen.omitidos += 1
        logger.warning("sync.jugador_no_encontrado", replay_id=replay_id)
        return False

    try:
        # `begin_nested` abre un savepoint: si algo falla, se deshace solo esta partida
        # y las anteriores siguen guardadas.
        async with session.begin_nested():
            await insertar_si_no_existe(
                session, Replay.__table__, _valores_replay(replay), ["ballchasing_id"]
            )

            for jugador in jugadores:
                await insertar_si_no_existe(
                    session,
                    PlayerStat.__table__,
                    _valores_stats(replay_id, jugador),
                    ["replay_id", "platform", "platform_id"],
                )
                await insertar_si_no_existe(
                    session,
                    UserReplay.__table__,
                    {
                        "id": uuid.uuid4(),
                        "user_id": user_id,
                        "replay_id": replay_id,
                        "game_account_id": jugador.game_account_id,
                        "team": jugador.team,
                        "result": calcular_resultado(
                            jugador.team, replay.blue_goals or 0, replay.orange_goals or 0
                        ),
                    },
                    ["user_id", "replay_id"],
                )
    except Exception:
        resumen.fallidos += 1
        logger.warning("sync.ingesta_fallida", replay_id=replay_id, exc_info=True)
        return False

    resumen.nuevos += 1
    if resumen.ultima_partida is None or replay.played_at > resumen.ultima_partida:
        resumen.ultima_partida = replay.played_at
    return True


def _valores_replay(replay: Replay) -> dict[str, Any]:
    return {
        "ballchasing_id": replay.ballchasing_id,
        "played_at": replay.played_at,
        "rocket_league_id": replay.rocket_league_id,
        "playlist_id": replay.playlist_id,
        "playlist_name": replay.playlist_name,
        "map_code": replay.map_code,
        "map_name": replay.map_name,
        "team_size": replay.team_size,
        "duration": replay.duration,
        "play_duration": replay.play_duration,
        "overtime": replay.overtime,
        "season": replay.season,
        "season_type": replay.season_type,
        "blue_goals": replay.blue_goals,
        "orange_goals": replay.orange_goals,
    }


def _valores_stats(replay_id: str, jugador: JugadorIdentificado) -> dict[str, Any]:
    return {
        "replay_id": replay_id,
        "platform": jugador.platform,
        "platform_id": jugador.platform_id,
        "name": jugador.name,
        "team": jugador.team,
        "mvp": jugador.mvp,
        **jugador.stats,
    }
