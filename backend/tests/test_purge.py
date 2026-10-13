"""Tests del borrado de datos de juego al eliminar una cuenta.

`DELETE /me` dice "borra cuenta y datos". Si al borrar la cuenta quedaran las
estadisticas del jugador, estarian en la base sin dueño: son datos personales de como
juega, y no los usa nadie mas.
"""

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GameAccount, PlayerStat, Replay, User, UserReplay
from tests.fakes import bearer


def _replay(replay_id: str, nombre: str = "partida") -> Replay:
    from datetime import UTC, datetime

    return Replay(
        ballchasing_id=replay_id,
        played_at=datetime(2024, 1, 1, tzinfo=UTC),
        playlist_id="ranked-duels",
        map_code="dfh_stadium",
        blue_goals=3,
        orange_goals=1,
    )


async def _datos_de_prueba(
    session: AsyncSession, platform: str = "steam", platform_id: str = "76561199000000001"
) -> tuple[User, GameAccount, Replay]:
    # `uid-alice` es el usuario que corresponde a `bearer("token-alice")`, que es quien
    # hace el DELETE: si no coinciden, se borraria una cuenta vacia.
    user = User(email="borrar@example.com", firebase_uid="uid-alice")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    cuenta = GameAccount(user_id=user.id, platform=platform, platform_id=platform_id)
    replay = _replay("aaaaaaaa-0000-4000-8000-000000000001")
    session.add_all([cuenta, replay])
    await session.commit()
    await session.refresh(cuenta)

    session.add(
        PlayerStat(
            replay_id=replay.ballchasing_id,
            platform=platform,
            platform_id=platform_id,
            name="Jugador1",
            team="blue",
            score=500,
        )
    )
    session.add(
        UserReplay(
            user_id=user.id,
            replay_id=replay.ballchasing_id,
            game_account_id=cuenta.id,
            team="blue",
            result="win",
        )
    )
    await session.commit()
    return user, cuenta, replay


async def test_borrar_el_usuario_borra_sus_estadisticas(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _datos_de_prueba(session)

    await client.request("DELETE", "/me", headers=bearer("token-alice"))

    assert await session.scalar(select(func.count()).select_from(PlayerStat)) == 0


async def test_borrar_el_usuario_borra_la_partida_sin_referencias(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Si nadie mas la referencia, la partida desaparece: no queda huerfana."""
    await _datos_de_prueba(session)

    await client.request("DELETE", "/me", headers=bearer("token-alice"))

    assert await session.scalar(select(func.count()).select_from(Replay)) == 0


async def test_no_se_borra_una_partida_que_usa_otro_usuario(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Dos usuarios pueden haber jugado la misma partida: esa se queda."""
    await _datos_de_prueba(session)

    # Otro usuario, mismo jugador en otra plataforma, jugando la misma partida.
    otro = User(email="otro@example.com", firebase_uid="uid-otro")
    session.add(otro)
    await session.commit()
    await session.refresh(otro)
    cuenta = GameAccount(user_id=otro.id, platform="epic", platform_id="epic-id-de-prueba-0001")
    session.add(cuenta)
    await session.commit()
    await session.refresh(cuenta)
    session.add(
        UserReplay(
            user_id=otro.id,
            replay_id="aaaaaaaa-0000-4000-8000-000000000001",
            game_account_id=cuenta.id,
            team="orange",
            result="loss",
        )
    )
    await session.commit()

    await client.request("DELETE", "/me", headers=bearer("token-alice"))

    assert await session.scalar(select(func.count()).select_from(Replay)) == 1


async def test_no_se_borran_las_estadisticas_de_otro_usuario(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Si otro usuario sigue jugando esa partida, la partida se queda y con ella
    sus estadisticas: solo se van las del usuario borrado."""
    await _datos_de_prueba(session)

    otro = User(email="otro@example.com", firebase_uid="uid-otro")
    session.add(otro)
    await session.commit()
    await session.refresh(otro)
    cuenta = GameAccount(user_id=otro.id, platform="steam", platform_id="76561199000000999")
    session.add(cuenta)
    await session.commit()
    await session.refresh(cuenta)

    session.add(
        PlayerStat(
            replay_id="aaaaaaaa-0000-4000-8000-000000000001",
            platform="steam",
            platform_id="76561199000000999",
            name="Otro",
            team="orange",
            score=400,
        )
    )
    session.add(
        UserReplay(
            user_id=otro.id,
            replay_id="aaaaaaaa-0000-4000-8000-000000000001",
            game_account_id=cuenta.id,
            team="orange",
            result="loss",
        )
    )
    await session.commit()

    await client.request("DELETE", "/me", headers=bearer("token-alice"))

    restantes = list(await session.scalars(select(PlayerStat)))
    assert len(restantes) == 1
    assert restantes[0].platform_id == "76561199000000999"


async def test_las_estadisticas_de_otros_desaparecen_si_la_partida_se_queda_rufia(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Sin nadie mas que referencie la partida, se borra entera y con ella todas sus
    estadisticas. No queda nada de esa partida en la base."""
    await _datos_de_prueba(session)
    session.add(
        PlayerStat(
            replay_id="aaaaaaaa-0000-4000-8000-000000000001",
            platform="steam",
            platform_id="76561199000000999",
            name="Rival",
            team="orange",
            score=400,
        )
    )
    await session.commit()

    await client.request("DELETE", "/me", headers=bearer("token-alice"))

    assert await session.scalar(select(func.count()).select_from(PlayerStat)) == 0
    assert await session.scalar(select(func.count()).select_from(Replay)) == 0
