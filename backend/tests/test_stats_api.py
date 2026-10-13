"""Tests de la API de datos: listado, detalle y estadisticas.

Se comprueba sobre todo el aislamiento entre usuarios y que los filtros del cliente
no puedan tocar la consulta.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GameAccount, PlayerStat, Replay, User, UserReplay
from tests.fakes import bearer

REPLAY_A = "aaaaaaaa-0000-4000-8000-000000000001"
REPLAY_B = "bbbbbbbb-0000-4000-8000-000000000002"
REPLAY_C = "cccccccc-0000-4000-8000-000000000003"
# Bob juega otras partidas: las suyas no pueden ser las mismas filas.
# Los ids son UUID de 36 caracteres, como los de Ballchasing. SQLite no valida
# la longitud de un varchar y Postgres si: por eso esto solo falla en Postgres.
REPLAY_B1 = "11111111-1111-4111-8111-111111111111"
REPLAY_B2 = "22222222-2222-4222-8222-222222222222"
REPLAY_B3 = "33333333-3333-4333-8333-333333333333"

FECHA_BASE = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _replay(replay_id: str, dias: int, playlist: str, *, goals: tuple[int, int] = (3, 1)) -> Replay:
    return Replay(
        ballchasing_id=replay_id,
        played_at=FECHA_BASE + timedelta(days=dias),
        playlist_id=playlist,
        playlist_name=playlist.replace("-", " ").title(),
        map_code="dfh_stadium",
        map_name="DFH Stadium",
        duration=380,
        play_duration=350,
        season=24,
        season_type="free2play",
        blue_goals=goals[0],
        orange_goals=goals[1],
    )


async def _poblar(
    session: AsyncSession,
    firebase_uid: str,
    platform_id: str,
    ids: tuple[str, str, str] = (REPLAY_A, REPLAY_B, REPLAY_C),
    escala: int = 1,
) -> User:
    """Crea un usuario con 3 partidas en dos playlists."""
    user = User(email=f"{firebase_uid}@example.com", firebase_uid=firebase_uid)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    cuenta = GameAccount(user_id=user.id, platform="steam", platform_id=platform_id)
    session.add(cuenta)
    await session.commit()
    await session.refresh(cuenta)

    partidas = [
        # Ganada en duelos, con datos de metricas nuevas.
        (
            _replay(ids[0], 0, "ranked-duels"),
            cuenta,
            "blue",
            "win",
            {
                "score": 520,
                "bpm": 400,
                "goals": 2,
                "goals_against": 1,
                "assists": 1,
                "saves": 3,
                "shots": 5,
                "demos_inflicted": 2,
                "demos_taken": 1,
                "centers": 4,
                "percent_full_boost": 25.5,
                "percent_zero_boost": 18.0,
                "avg_speed": 1550,
                "percent_ground": 48.0,
                "percent_supersonic_speed": 12.0,
            },
        ),
        # Perdida en duelos.
        (
            _replay(ids[1], 7, "ranked-duels", goals=(1, 4)),
            cuenta,
            "orange",
            "loss",
            {
                "score": 310,
                "bpm": 340,
                "goals": 1,
                "goals_against": 4,
                "assists": 0,
                "saves": 2,
                "shots": 2,
                "demos_inflicted": 0,
                "demos_taken": 3,
                "centers": None,
                "percent_full_boost": 15.0,
                "percent_zero_boost": 30.0,
                "avg_speed": 1400,
                "percent_ground": 52.0,
                "percent_supersonic_speed": 5.0,
            },
        ),
        # Ganada en standard, con stats de un replay viejo: `centers` en None.
        (
            _replay(ids[2], 14, "ranked-standard"),
            cuenta,
            "blue",
            "win",
            {
                "score": 610,
                "bpm": 420,
                "goals": 1,
                "goals_against": 1,
                "assists": 2,
                "saves": 5,
                "shots": 4,
                "demos_inflicted": 3,
                "demos_taken": 0,
                "centers": None,
                "percent_full_boost": 30.0,
                "percent_zero_boost": 12.0,
                "avg_speed": 1600,
                "percent_ground": 45.0,
                "percent_supersonic_speed": 15.0,
            },
        ),
    ]

    for replay, cuenta_jugador, equipo, resultado, stats in partidas:
        stats = {**stats}
        if escala != 1:
            stats["score"] = stats["score"] * escala
            stats["bpm"] = stats["bpm"] * escala
        session.add(replay)
        await session.commit()
        session.add(
            PlayerStat(
                replay_id=replay.ballchasing_id,
                platform=cuenta_jugador.platform,
                platform_id=cuenta_jugador.platform_id,
                name="Jugador",
                team=equipo,
                **stats,
            )
        )
        session.add(
            UserReplay(
                user_id=user.id,
                replay_id=replay.ballchasing_id,
                game_account_id=cuenta_jugador.id,
                team=equipo,
                result=resultado,
            )
        )
        await session.commit()

    return user


@pytest.fixture
async def alice(session: AsyncSession) -> User:
    return await _poblar(session, "uid-alice", "steam-alice")


@pytest.fixture
async def bob(session: AsyncSession) -> User:
    return await _poblar(
        session, "uid-bob", "steam-bob", ids=(REPLAY_B1, REPLAY_B2, REPLAY_B3), escala=2
    )


# --- listado ---


async def test_listar_replays(client: AsyncClient, alice: User, bob: User) -> None:
    response = await client.get("/replays", headers=bearer("token-alice"))

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["total"] == 3
    assert len(cuerpo["items"]) == 3


async def test_lista_de_la_mas_reciente_a_la_mas_antigua(client: AsyncClient, alice: User) -> None:
    cuerpo = (await client.get("/replays", headers=bearer("token-alice"))).json()

    fechas = [item["played_at"] for item in cuerpo["items"]]
    assert fechas == sorted(fechas, reverse=True)


async def test_cada_usuario_solo_ve_sus_partidas(
    client: AsyncClient, alice: User, bob: User, session: AsyncSession
) -> None:
    cuerpo = (await client.get("/replays", headers=bearer("token-bob"))).json()

    assert cuerpo["total"] == 3
    # Las partidas de Bob son las suyas, no las de Alice.
    assert {item["id"] for item in cuerpo["items"]} == {REPLAY_B1, REPLAY_B2, REPLAY_B3}


async def test_usuario_sin_datos_devuelve_lista_vacia(client: AsyncClient) -> None:
    """Un usuario nuevo no tiene error: ve una lista vacia."""
    response = await client.get("/replays", headers=bearer("token-bob"))

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


async def test_filtrar_por_resultado(client: AsyncClient, alice: User) -> None:
    cuerpo = (await client.get("/replays?result=win", headers=bearer("token-alice"))).json()

    assert cuerpo["total"] == 2
    assert all(item["result"] == "win" for item in cuerpo["items"])


async def test_filtrar_por_playlist(client: AsyncClient, alice: User) -> None:
    cuerpo = (
        await client.get("/replays?playlist=ranked-duels", headers=bearer("token-alice"))
    ).json()

    assert cuerpo["total"] == 2


async def test_filtrar_por_rango_de_fechas(client: AsyncClient, alice: User) -> None:
    cuerpo = (
        await client.get(
            "/replays?desde=2026-03-10&hasta=2026-03-31", headers=bearer("token-alice")
        )
    ).json()

    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["id"] == REPLAY_C


async def test_filtrar_hasta_incluye_el_dia_completo(client: AsyncClient, alice: User) -> None:
    """`hasta=2026-03-01` debe incluir la partida de ese dia, no solo las 00:00."""
    cuerpo = (await client.get("/replays?hasta=2026-03-01", headers=bearer("token-alice"))).json()

    assert cuerpo["total"] == 1


async def test_resultado_invalido_da_422(client: AsyncClient, alice: User) -> None:
    response = await client.get("/replays?result=ganada", headers=bearer("token-alice"))

    assert response.status_code == 422


async def test_fecha_invalida_da_422(client: AsyncClient, alice: User) -> None:
    response = await client.get("/replays?desde=ayer", headers=bearer("token-alice"))

    assert response.status_code == 422


async def test_paginacion(client: AsyncClient, alice: User) -> None:
    primera = (await client.get("/replays?limit=2", headers=bearer("token-alice"))).json()
    segunda = (await client.get("/replays?limit=2&offset=2", headers=bearer("token-alice"))).json()

    assert primera["total"] == segunda["total"] == 3
    assert len(primera["items"]) == 2
    assert len(segunda["items"]) == 1
    ids_primera = {i["id"] for i in primera["items"]}
    ids_segunda = {i["id"] for i in segunda["items"]}
    assert not ids_primera & ids_segunda


async def test_limite_maximo(client: AsyncClient, alice: User) -> None:
    response = await client.get("/replays?limit=9999", headers=bearer("token-alice"))

    assert response.status_code == 422


# --- detalle ---


async def test_detalle_de_una_partida(client: AsyncClient, alice: User) -> None:
    response = await client.get(f"/replays/{REPLAY_A}", headers=bearer("token-alice"))

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["replay"]["id"] == REPLAY_A
    assert cuerpo["replay"]["result"] == "win"
    assert cuerpo["stats"][0]["score"] == 520
    assert cuerpo["duration"] == 380


async def test_detalle_de_partida_ajena_da_404(client: AsyncClient, alice: User) -> None:
    """Bob no puede leer una partida de Alice: no existe para el."""
    response = await client.get(f"/replays/{REPLAY_A}", headers=bearer("token-bob"))

    assert response.status_code == 404


async def test_detalle_inexistente_da_404(client: AsyncClient, alice: User) -> None:
    response = await client.get("/replays/no-existe", headers=bearer("token-alice"))

    assert response.status_code == 404


async def test_detalle_tolera_metricas_nulas(client: AsyncClient, alice: User) -> None:
    """`centers` es None en el replay viejo: la respuesta debe incluirlo, no fallar."""
    cuerpo = (await client.get(f"/replays/{REPLAY_B}", headers=bearer("token-alice"))).json()

    assert cuerpo["stats"][0]["centers"] is None
    assert cuerpo["stats"][0]["score"] == 310


# --- resumen ---


async def test_resumen_agrega_los_datos(client: AsyncClient, alice: User) -> None:
    response = await client.get("/stats/summary", headers=bearer("token-alice"))

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["replays"] == 3
    assert cuerpo["wins"] == 2
    assert cuerpo["losses"] == 1
    assert cuerpo["ties"] == 0
    # 2 victorias de 3 partidas con resultado claro.
    assert cuerpo["win_rate"] == 66.67
    assert cuerpo["goals"] == 4
    assert cuerpo["goals_against"] == 6  # 1 + 4 + 1


async def test_resumen_calcula_medias(client: AsyncClient, alice: User) -> None:
    cuerpo = (await client.get("/stats/summary", headers=bearer("token-alice"))).json()

    assert cuerpo["avg_score"] == 480.0
    assert cuerpo["avg_bpm"] == 386.67


async def test_resumen_desglosa_por_playlist(client: AsyncClient, alice: User) -> None:
    cuerpo = (await client.get("/stats/summary", headers=bearer("token-alice"))).json()

    por_id = {p["playlist_id"]: p for p in cuerpo["por_playlist"]}
    assert por_id["ranked-duels"]["replays"] == 2
    assert por_id["ranked-duels"]["wins"] == 1
    assert por_id["ranked-duels"]["win_rate"] == 50.0
    assert por_id["ranked-standard"]["replays"] == 1


async def test_resumen_filtrado_por_playlist(client: AsyncClient, alice: User) -> None:
    cuerpo = (
        await client.get("/stats/summary?playlist=ranked-standard", headers=bearer("token-alice"))
    ).json()

    assert cuerpo["replays"] == 1
    assert cuerpo["wins"] == 1


async def test_resumen_de_usuario_sin_datos(client: AsyncClient) -> None:
    cuerpo = (await client.get("/stats/summary", headers=bearer("token-bob"))).json()

    assert cuerpo["replays"] == 0
    assert cuerpo["win_rate"] is None
    assert cuerpo["avg_score"] is None


async def test_resumen_solo_usa_datos_del_usuario(
    client: AsyncClient, alice: User, bob: User
) -> None:
    """Bob tambien tiene 3 partidas, pero su resumen no puede incluir las de Alice."""
    cuerpo = (await client.get("/stats/summary", headers=bearer("token-bob"))).json()

    assert cuerpo["replays"] == 3


# --- tendencias ---


async def test_tendencias_por_semana(client: AsyncClient, alice: User) -> None:
    response = await client.get(
        "/stats/trends?metric=score&interval=week", headers=bearer("token-alice")
    )

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["metrica"] == "score"
    assert cuerpo["intervalo"] == "week"
    assert len(cuerpo["puntos"]) >= 2


async def test_tendencias_devuelve_la_media_del_periodo(client: AsyncClient, alice: User) -> None:
    cuerpo = (
        await client.get("/stats/trends?metric=score&interval=month", headers=bearer("token-alice"))
    ).json()

    punto = cuerpo["puntos"][0]
    assert punto["periodo"] == "2026-03-01"
    # Las tres partidas caen en marzo: 520, 310 y 610 -> media 480.
    assert punto["valor"] == 480.0
    assert punto["total"] == 1440.0
    assert punto["replays"] == 3


async def test_tendencias_omite_los_periodos_sin_datos(client: AsyncClient, alice: User) -> None:
    """Sin datos no se inventa un 0: aparecerian como caidas en la grafica."""
    cuerpo = (
        await client.get("/stats/trends?metric=score&interval=week", headers=bearer("token-alice"))
    ).json()

    assert all(punto["valor"] is not None for punto in cuerpo["puntos"])


async def test_tendencias_con_metrica_invalida_da_422(client: AsyncClient, alice: User) -> None:
    """La metrica es una lista cerrada: nunca llega a la consulta como texto."""
    response = await client.get(
        "/stats/trends?metric=score; DROP TABLE users", headers=bearer("token-alice")
    )

    assert response.status_code == 422


async def test_tendencias_con_intervalo_invalido_da_422(client: AsyncClient, alice: User) -> None:
    response = await client.get(
        "/stats/trends?metric=score&interval=trimestre", headers=bearer("token-alice")
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "metrica",
    ["bpm", "percent_full_boost", "percent_zero_boost", "centers", "demos_inflicted"],
)
async def test_todas_las_metricas_son_consultables(
    client: AsyncClient, alice: User, metrica: str
) -> None:
    response = await client.get(f"/stats/trends?metric={metrica}", headers=bearer("token-alice"))

    assert response.status_code == 200


async def test_tendencias_no_mezcla_usuarios(client: AsyncClient, alice: User, bob: User) -> None:
    """Bob tiene el doble de puntuacion; si se mezclaran datos, se notaria."""
    alice_puntos = (
        await client.get("/stats/trends?metric=score", headers=bearer("token-alice"))
    ).json()["puntos"]
    bob_puntos = (
        await client.get("/stats/trends?metric=score", headers=bearer("token-bob"))
    ).json()["puntos"]

    assert max(p["valor"] for p in alice_puntos) == 610.0
    assert max(p["valor"] for p in bob_puntos) == 1220.0


# --- autenticacion ---


@pytest.mark.parametrize(
    "ruta",
    ["/replays", "/replays/abc", "/stats/summary", "/stats/trends?metric=score"],
)
async def test_las_rutas_de_datos_exigen_token(client: AsyncClient, ruta: str) -> None:
    response = await client.get(ruta)

    assert response.status_code == 401
