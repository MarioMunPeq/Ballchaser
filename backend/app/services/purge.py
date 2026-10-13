"""Borrado de los datos de juego de un usuario.

`DELETE /me` dice "borra cuenta y datos". Borrar solo la cuenta dejaria en la base las
estadisticas de ese jugador: son suyas, identifican como juegas y no las usa nadie mas.
Por eso hay que llevarselas tambien.

`replays` y `player_stats` no cuelgan de ningun usuario (dos usuarios pueden haber
jugado la misma partida), asi que no se borran en cascada. Se limpian de forma
explicita y en este orden: primero las filas que son solo suyas, luego las partidas que
se quedan sin ninguna referencia.
"""

import uuid

from sqlalchemy import delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.game_account import GameAccount
from app.db.models.replay import PlayerStat, Replay, UserReplay


async def borrar_datos_de_juego(session: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    """Borra las estadisticas del usuario y las partidas que quedan huerfanas.

    Devuelve cuantos filas se han borrado de cada tipo, para poder comprobarlo.
    """
    identidades = list(
        (
            await session.execute(
                select(GameAccount.platform, GameAccount.platform_id).where(
                    GameAccount.user_id == user_id
                )
            )
        ).all()
    )

    stats_borradas = 0
    if identidades:
        resultado = await session.execute(
            delete(PlayerStat).where(
                tuple_(PlayerStat.platform, PlayerStat.platform_id).in_(identidades)
            )
        )
        stats_borradas = resultado.rowcount or 0

    # Los vinculos con partidas se van antes de comprobar que partidas sobran.
    await session.execute(delete(UserReplay).where(UserReplay.user_id == user_id))

    # Partidas que ya no referencia ningun usuario.
    resultado = await session.execute(
        delete(Replay).where(Replay.ballchasing_id.not_in(select(UserReplay.replay_id)))
    )
    replays_borrados = resultado.rowcount or 0

    await session.commit()
    return {
        "player_stats": stats_borradas,
        "replays": replays_borrados,
    }
