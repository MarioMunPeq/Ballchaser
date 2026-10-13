"""Tests de la ingesta de replays.

Los fixtures vienen de una respuesta real de Ballchasing (anonimizada) guardada en
`tests/fixtures/`, no de un JSON inventado: asi los tests fallan si la API cambia de
forma.
"""

import copy
import json
import re
import uuid
from datetime import UTC
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GameAccount, PlayerStat, Replay, User, UserReplay
from app.services import ingest
from app.services.ballchasing import ClienteBallchasing

BASE = "https://ballchasing.com/api"
FIXTURES = Path(__file__).parent / "fixtures"

STEAM_ID = "76561199000000001"
EPIC_ID = "epic-id-de-prueba-0001"


# Solo el endpoint de listado (`/replays` o `/replays?...`), nunca el detalle
# (`/replays/<id>`): si se mezcla, el detalle devuelve el listado y todo falla.
LISTADO = rf"{re.escape(BASE)}/replays(\?.*)?$"
DETALLE = rf"{re.escape(BASE)}/replays/[^?]+"


def _fixture() -> dict[str, Any]:
    return json.loads((FIXTURES / "replay_detalle.json").read_text(encoding="utf-8"))


@pytest.fixture
def detalle_real() -> dict[str, Any]:
    return _fixture()


@pytest.fixture
async def usuario(session: AsyncSession) -> User:
    user = User(email="test@example.com", firebase_uid="uid-ingesta")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
async def cuentas(session: AsyncSession, usuario: User) -> list[GameAccount]:
    a = GameAccount(
        user_id=usuario.id, platform="steam", platform_id=STEAM_ID, display_name="Jugador1"
    )
    b = GameAccount(user_id=usuario.id, platform="epic", platform_id=EPIC_ID)
    session.add_all([a, b])
    await session.commit()
    await session.refresh(a)
    await session.refresh(b)
    return [a, b]


@pytest.fixture
def cliente() -> ClienteBallchasing:
    return ClienteBallchasing(
        "token-de-prueba",
        cliente_http=httpx.AsyncClient(base_url=BASE),
        max_intentos=1,
        espera_base=0.001,
    )


def _listado(*ids: str, siguiente: str | None = None) -> dict[str, Any]:
    """Listado con la forma real: `list` / `count` / `next`."""
    cuerpo: dict[str, Any] = {
        "list": [{"id": i, "date": "2023-10-09T20:50:00Z"} for i in ids],
        "count": len(ids),
    }
    if siguiente:
        cuerpo["next"] = siguiente
    return cuerpo


# --- aplanado de estadisticas ---


def test_el_fixture_real_tiene_los_grupos_esperados(detalle_real: dict[str, Any]) -> None:
    """Si Ballchasing renombra un grupo, este test avisa antes de romper la ingesta."""
    jugador = detalle_real["blue"]["players"][0]
    assert set(jugador["stats"]) == {"core", "boost", "movement", "positioning", "demo"}


def test_el_grupo_de_demos_se_llama_demo_en_singular(detalle_real: dict[str, Any]) -> None:
    """La guia lo llamaba `demos_inflicted_def_half`; en la API es `demo`."""
    jugador = detalle_real["blue"]["players"][0]
    assert "inflicted" in jugador["stats"]["demo"]


def test_un_replay_de_2023_no_tiene_las_metricas_recientes(detalle_real: dict[str, Any]) -> None:
    """Las columnas 'solo recientes' deben salir en None, no en 0."""
    jugador = detalle_real["blue"]["players"][0]
    stats = ingest.aplanar_stats(jugador)

    assert stats["demos_inflicted"] is not None
    assert stats["epic_saves"] is None
    assert stats["centers"] is None


def test_aplana_las_metricas_principales(detalle_real: dict[str, Any]) -> None:
    jugador = detalle_real["blue"]["players"][0]
    stats = ingest.aplanar_stats(jugador)

    assert stats["score"] == jugador["stats"]["core"]["score"]
    assert stats["bpm"] == jugador["stats"]["boost"]["bpm"]
    assert stats["avg_speed"] == jugador["stats"]["movement"]["avg_speed"]
    assert (
        stats["percent_defensive_third"]
        == jugador["stats"]["positioning"]["percent_defensive_third"]
    )


def test_un_jugador_sin_stats_no_revienta(detalle_real: dict[str, Any]) -> None:
    stats = ingest.aplanar_stats({"stats": {}})
    assert stats["score"] is None


def test_mvp_solo_existe_en_el_jugador_mvp(detalle_real: dict[str, Any]) -> None:
    """La API no manda la clave `mvp` en el resto: se lee con .get()."""
    encontrados = [
        jugador for equipo in ("blue", "orange") for jugador in detalle_real[equipo]["players"]
    ]
    con_clave = [j for j in encontrados if "mvp" in j]
    assert con_clave, "el fixture deberia traer al menos un MVP"
    assert len(con_clave) <= 1


def test_parsea_la_fecha_rfc3339_con_z(detalle_real: dict[str, Any]) -> None:
    fecha = ingest.parsear_fecha(detalle_real["date"])
    assert fecha.tzinfo is not None
    assert fecha.astimezone(UTC) == fecha


# --- analisis del detalle ---


def test_solo_selecciona_los_jugadores_del_usuario(detalle_real: dict[str, Any]) -> None:
    """De 6 jugadores, solo se guardan los que son cuentas del usuario."""
    _replay, jugadores = ingest.analizar_detalle(detalle_real, _cuentas())

    assert {j.platform_id for j in jugadores} == {STEAM_ID, EPIC_ID}
    assert len(jugadores) == 2


def test_el_replay_trae_los_goles_por_equipo(detalle_real: dict[str, Any]) -> None:
    """Los goles estan en blue.stats.core.goals, no en la raiz."""
    replay, _ = ingest.analizar_detalle(detalle_real, _cuentas())

    assert replay.blue_goals == detalle_real["blue"]["stats"]["core"]["goals"]
    assert replay.orange_goals == detalle_real["orange"]["stats"]["core"]["goals"]


@pytest.mark.parametrize(
    ("team", "esperado"),
    [("blue", "win"), ("orange", "loss")],
)
def test_resultado_segun_los_goles(team: str, esperado: str) -> None:
    assert ingest.calcular_resultado(team, goles_blue=3, goles_orange=1) == esperado


def test_empate_cuando_los_goles_son_iguales() -> None:
    assert ingest.calcular_resultado("blue", 2, 2) == "tie"
    assert ingest.calcular_resultado("orange", 2, 2) == "tie"


# --- ingesta de punta a punta ---


async def test_ingiere_una_partida_nueva(
    session: AsyncSession,
    cliente: ClienteBallchasing,
    usuario: User,
    cuentas: list[GameAccount],
    detalle_real: dict[str, Any],
) -> None:
    replay_id = detalle_real["id"]
    with respx.mock:
        respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json=_listado(replay_id))
        )
        respx.get(f"{BASE}/replays/{replay_id}").mock(
            return_value=httpx.Response(200, json=detalle_real)
        )
        resumen = await ingest.sincronizar(session, cliente, cuentas, usuario.id)

    assert resumen.nuevos == 1
    assert resumen.fallidos == 0

    replay = await session.get(Replay, replay_id)
    assert replay is not None
    stats = await session.scalars(select(PlayerStat))
    assert len(list(stats)) == 2, "solo los dos jugadores del usuario"
    vinculos = await session.scalars(select(UserReplay))
    assert len(list(vinculos)) == 1


async def test_ingesta_es_idempotente(
    session: AsyncSession,
    cliente: ClienteBallchasing,
    usuario: User,
    cuentas: list[GameAccount],
    detalle_real: dict[str, Any],
) -> None:
    """Ejecutar dos veces no duplica nada: es lo que permite reintentar sin miedo."""
    replay_id = detalle_real["id"]
    with respx.mock:
        respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json=_listado(replay_id))
        )
        detalle = respx.get(f"{BASE}/replays/{replay_id}").mock(
            return_value=httpx.Response(200, json=detalle_real)
        )
        primera = await ingest.sincronizar(session, cliente, cuentas, usuario.id)
        segunda = await ingest.sincronizar(session, cliente, cuentas, usuario.id)

    assert primera.nuevos == 1
    assert segunda.nuevos == 0
    assert segunda.omitidos == 1
    assert detalle.call_count == 1, "no se vuelve a pedir el detalle de algo ya guardado"
    assert await session.scalar(select(func.count()).select_from(Replay)) == 1


async def test_no_pide_el_detalle_de_lo_ya_guardado(
    session: AsyncSession,
    cliente: ClienteBallchasing,
    usuario: User,
    cuentas: list[GameAccount],
    detalle_real: dict[str, Any],
) -> None:
    """Ahorrar cuota es la razon de mirar antes de pedir."""
    replay_id = detalle_real["id"]
    with respx.mock:
        respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json=_listado(replay_id))
        )
        detalle = respx.get(f"{BASE}/replays/{replay_id}").mock(
            return_value=httpx.Response(200, json=detalle_real)
        )
        await ingest.sincronizar(session, cliente, cuentas, usuario.id)
        await ingest.sincronizar(session, cliente, cuentas, usuario.id)

    assert detalle.call_count == 1


async def test_ignora_replays_pendientes(
    session: AsyncSession,
    cliente: ClienteBallchasing,
    usuario: User,
    cuentas: list[GameAccount],
    detalle_real: dict[str, Any],
) -> None:
    """`status` distinto de `ok` no tiene estadisticas: no se guarda nada."""
    pendiente = copy.deepcopy(detalle_real)
    pendiente["status"] = "pending"
    replay_id = pendiente["id"]

    with respx.mock:
        respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json=_listado(replay_id))
        )
        respx.get(f"{BASE}/replays/{replay_id}").mock(
            return_value=httpx.Response(200, json=pendiente)
        )
        resumen = await ingest.sincronizar(session, cliente, cuentas, usuario.id)

    assert resumen.nuevos == 0
    assert resumen.omitidos == 1
    assert await session.scalar(select(func.count()).select_from(Replay)) == 0


async def test_un_replay_pendiente_se_reintenta_mas_adelante(
    session: AsyncSession,
    cliente: ClienteBallchasing,
    usuario: User,
    cuentas: list[GameAccount],
    detalle_real: dict[str, Any],
) -> None:
    """Al no guardarse nada, la proxima pasada vuelve a mirarlo."""
    pendiente = copy.deepcopy(detalle_real)
    pendiente["status"] = "pending"
    replay_id = pendiente["id"]

    with respx.mock:
        respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json=_listado(replay_id))
        )
        detalle = respx.get(f"{BASE}/replays/{replay_id}").mock(
            side_effect=[
                httpx.Response(200, json=pendiente),
                httpx.Response(200, json=detalle_real),
            ]
        )
        await ingest.sincronizar(session, cliente, cuentas, usuario.id)
        segunda = await ingest.sincronizar(session, cliente, cuentas, usuario.id)

    assert segunda.nuevos == 1
    assert detalle.call_count == 2


async def test_una_partida_que_falla_no_tira_el_resto(
    session: AsyncSession,
    cliente: ClienteBallchasing,
    usuario: User,
    cuentas: list[GameAccount],
    detalle_real: dict[str, Any],
) -> None:
    buena = detalle_real["id"]
    mala = "00000000-0000-4000-8000-00000000dead"

    with respx.mock:
        respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json=_listado(mala, buena))
        )
        respx.get(f"{BASE}/replays/{mala}").mock(side_effect=httpx.ConnectError("se cayo"))
        respx.get(f"{BASE}/replays/{buena}").mock(
            return_value=httpx.Response(200, json=detalle_real)
        )
        resumen = await ingest.sincronizar(session, cliente, cuentas, usuario.id)

    assert resumen.nuevos == 1
    assert resumen.fallidos == 1
    assert await session.scalar(select(func.count()).select_from(Replay)) == 1


async def test_seguiente_sin_mas_paginas(
    session: AsyncSession,
    cliente: ClienteBallchasing,
    usuario: User,
    cuentas: list[GameAccount],
    detalle_real: dict[str, Any],
) -> None:
    """Sin `next` en la respuesta, se para: no se inventa una URL."""
    with respx.mock:
        respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json=_listado(detalle_real["id"]))
        )
        respx.get(f"{BASE}/replays/{detalle_real['id']}").mock(
            return_value=httpx.Response(200, json=detalle_real)
        )
        resumen = await ingest.sincronizar(session, cliente, cuentas, usuario.id)

    assert resumen.paginas == 1


async def test_sigue_el_enlace_next_sin_anadir_parametros(
    session: AsyncSession,
    cliente: ClienteBallchasing,
    usuario: User,
    cuentas: list[GameAccount],
    detalle_real: dict[str, Any],
) -> None:
    """Mezclar `count` con `next` haria que la API ignorase el cursor."""
    segunda_pagina = f"{BASE}/replays?after=cursor&count=200"
    primera = _listado("00000000-0000-4000-8000-00000000aaaa", siguiente=segunda_pagina)
    segunda = _listado(detalle_real["id"])
    peticiones: list[str] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        url = str(peticion.url)
        peticiones.append(url)
        if "after=" in url:
            return httpx.Response(200, json=segunda)
        return httpx.Response(200, json=primera)

    with respx.mock:
        # Un solo mock que decide por URL: dos rutas con el mismo path se pisan.
        respx.get(url__regex=LISTADO).mock(side_effect=responder)
        respx.get(f"{BASE}/replays/00000000-0000-4000-8000-00000000aaaa").mock(
            return_value=httpx.Response(500)
        )
        respx.get(f"{BASE}/replays/{detalle_real['id']}").mock(
            return_value=httpx.Response(200, json=detalle_real)
        )
        resumen = await ingest.sincronizar(session, cliente, cuentas, usuario.id)

    assert resumen.paginas == 2
    assert resumen.nuevos == 1
    assert peticiones[1] == segunda_pagina, "el enlace next se pide tal cual"


async def test_para_cuando_no_hay_nada_nuevo(
    session: AsyncSession,
    cliente: ClienteBallchasing,
    usuario: User,
    cuentas: list[GameAccount],
) -> None:
    """No debe recorrer 10.000 paginas de partidas ya conocidas."""
    pagina_vacia = {
        "list": [{"id": f"00000000-0000-4000-8000-{i:012d}"} for i in range(2)],
        "count": 2,
        "next": f"{BASE}/replays?after=cursor&count=200",
    }
    paginas_pedidas: list[str] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        paginas_pedidas.append(str(peticion.url))
        return httpx.Response(200, json=pagina_vacia)

    with respx.mock:
        # Ninguna de estas partidas esta en la base, asi que fallan y no cuentan como
        # nuevas: se simula el caso real de "todo lo que veo ya lo conozco".
        respx.get(url__regex=LISTADO).mock(side_effect=responder)
        respx.get(url__regex=DETALLE).mock(
            return_value=httpx.Response(200, json={"status": "pending"})
        )
        resumen = await ingest.sincronizar(session, cliente, cuentas, usuario.id)

    assert resumen.paginas == ingest.PAGINAS_SIN_NUEVOS_PARA_PARAR
    assert len(paginas_pedidas) == ingest.PAGINAS_SIN_NUEVOS_PARA_PARAR, "no recorre sin fin"


async def test_sin_cuentas_no_hace_nada(
    session: AsyncSession,
    cliente: ClienteBallchasing,
    usuario: User,
    cuentas: list[GameAccount],
) -> None:
    with respx.mock:
        listado = respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json=_listado())
        )
        resumen = await ingest.sincronizar(session, cliente, [], usuario.id)

    assert resumen.nuevos == 0
    assert listado.call_count == 0, "sin cuentas no se gasta cuota"


async def test_filtra_por_los_player_id_de_las_cuentas(
    session: AsyncSession,
    cliente: ClienteBallchasing,
    usuario: User,
    cuentas: list[GameAccount],
) -> None:
    """Se piden las partidas del jugador, no las que subio su cuenta."""
    with respx.mock:
        ruta = respx.get(f"{BASE}/replays").mock(return_value=httpx.Response(200, json=_listado()))
        await ingest.sincronizar(session, cliente, cuentas, usuario.id)

    pedidos = ruta.calls.last.request.url.params.get_list("player-id")
    assert sorted(pedidos) == sorted([f"steam:{STEAM_ID}", f"epic:{EPIC_ID}"])


def _cuentas() -> list[GameAccount]:
    """Cuentas en memoria, sin tocar la base: solo hacen falta sus ids."""
    return [
        GameAccount(
            id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            platform="steam",
            platform_id=STEAM_ID,
        ),
        GameAccount(
            id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            platform="epic",
            platform_id=EPIC_ID,
        ),
    ]
