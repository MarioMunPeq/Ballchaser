"""Tests del cliente de Ballchasing: forma de la API, 429 y token invalido.

Ballchasing se simula con `respx`, sin tocar la red.
"""

import httpx
import pytest
import respx

from app.services.ballchasing import (
    ClienteBallchasing,
    CuotaAgotada,
    ErrorBallchasing,
    TokenInvalido,
    id_de_plataforma,
    validar_formato_de_token,
)
from app.services.ballchasing.rate_limit import BolsaDeTokens, LimitadorDePeticiones

BASE = "https://ballchasing.com/api"


@pytest.fixture
def cliente() -> ClienteBallchasing:
    """Cliente con limitador sin esperas, para que los tests no tarden."""
    return ClienteBallchasing(
        "token-de-prueba",
        cliente_http=httpx.AsyncClient(base_url=BASE),
        limitador=LimitadorDePeticiones(por_segundo=1000, por_hora=1000, por_dia=1000),
        # Backoff casi nulo: si no, los tests de reintento tardarian segundos.
        espera_base=0.001,
    )


async def test_listar_usa_la_forma_real_de_la_respuesta(cliente: ClienteBallchasing) -> None:
    """La API devuelve 'list'/'count'/'next', no 'replays'/'meta'."""
    cuerpo = {"list": [{"id": "abc"}], "count": 1, "next": None}
    with respx.mock:
        respx.get(f"{BASE}/replays").mock(return_value=httpx.Response(200, json=cuerpo))
        datos = await cliente.listar_replays(limit=1)

    assert datos["list"][0]["id"] == "abc"
    assert "replays" not in datos


async def test_listar_manda_solo_mios_como_uploader_me(cliente: ClienteBallchasing) -> None:
    with respx.mock:
        ruta = respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json={"list": [], "count": 0})
        )
        await cliente.listar_replays(limit=1, solo_mios=True)

    assert ruta.calls.last.request.url.params["uploader"] == "me"


async def test_listar_no_inventa_player_name(cliente: ClienteBallchasing) -> None:
    """Comprobado en el servicio real: `uploader=me` va solo, sin `player-name`."""
    with respx.mock:
        ruta = respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json={"list": []})
        )
        await cliente.listar_replays(limit=1, solo_mios=True)

    params = ruta.calls.last.request.url.params
    assert "player-name" not in params


@pytest.mark.parametrize(
    ("kwargs", "param_esperado"),
    [
        ({"playlist": "unranked-standard"}, "playlist"),
        ({"season": 24}, "season"),
        ({"despues_de": "2026-01-01T00:00:00Z"}, "replay-date-after"),
        ({"antes_de": "2026-01-01T00:00:00Z"}, "replay-date-before"),
    ],
)
async def test_listar_manda_los_filtros(
    cliente: ClienteBallchasing, kwargs: dict, param_esperado: str
) -> None:
    with respx.mock:
        ruta = respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json={"list": []})
        )
        await cliente.listar_replays(limit=1, **kwargs)

    assert param_esperado in ruta.calls.last.request.url.params


async def test_listar_por_identificador_de_jugador(cliente: ClienteBallchasing) -> None:
    """Filtra por `steam:<id>`, no por nombre: el nombre puede cambiar."""
    with respx.mock:
        ruta = respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json={"list": [], "count": 0})
        )
        await cliente.listar_replays(limit=5, player_ids=["steam:76561199085282414"])

    assert ruta.calls.last.request.url.params["player-id"] == "steam:76561199085282414"


async def test_listar_con_varias_cuentas_repite_el_parametro(
    cliente: ClienteBallchasing,
) -> None:
    """Con varias cuentas se manda `player-id` repetido, no una lista en un valor."""
    with respx.mock:
        ruta = respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json={"list": []})
        )
        await cliente.listar_replays(limit=5, player_ids=["steam:111", "epic:222"])

    assert ruta.calls.last.request.url.params.get_list("player-id") == ["steam:111", "epic:222"]


@pytest.mark.parametrize(
    ("platform", "platform_id", "esperado"),
    [
        ("steam", "76561199085282414", "steam:76561199085282414"),
        ("Steam", "76561199085282414", "steam:76561199085282414"),
        ("ps4", "gamertag", "ps4:gamertag"),
        ("steam", " 123 ", "steam:123"),
    ],
)
def test_id_de_plataforma(platform: str, platform_id: str, esperado: str) -> None:
    assert id_de_plataforma(platform, platform_id) == esperado


@pytest.mark.parametrize(("platform", "platform_id"), [("steam", ""), ("", "123")])
def test_id_de_plataforma_rechaza_vacios(platform: str, platform_id: str) -> None:
    with pytest.raises(ValueError, match="obligatorios"):
        id_de_plataforma(platform, platform_id)


async def test_seguir_next_no_añade_parametros(cliente: ClienteBallchasing) -> None:
    """Mezclar `count` con `next` hace que la API ignorare el cursor."""
    siguiente = f"{BASE}/replays?after=abc&count=200"

    with respx.mock:
        ruta = respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json={"list": [{"id": "nuevo"}]})
        )
        datos = await cliente.listar_replays(siguiente=siguiente)

    assert datos["list"][0]["id"] == "nuevo"
    assert ruta.calls.last.request.url.params["after"] == "abc"
    assert ruta.calls.last.request.url.params["count"] == "200"


@pytest.mark.parametrize("limite", [0, 201, 500])
async def test_limite_fuera_de_rango_falla_sin_pedir(
    cliente: ClienteBallchasing, limite: int
) -> None:
    with respx.mock, pytest.raises(ValueError, match="entre 1 y 200"):
        await cliente.listar_replays(limit=limite)


async def test_obtener_replay_devuelve_el_objeto_plano(cliente: ClienteBallchasing) -> None:
    """El detalle no viene envuelto en 'replay': los equipos son blue y orange."""
    cuerpo = {"id": "abc", "status": "ok", "blue": {"players": []}, "orange": {"players": []}}
    with respx.mock:
        respx.get(f"{BASE}/replays/abc").mock(return_value=httpx.Response(200, json=cuerpo))
        datos = await cliente.obtener_replay("abc")

    assert datos["status"] == "ok"
    assert "replay" not in datos


async def test_token_invalido_da_401_sin_reintentar(cliente: ClienteBallchasing) -> None:
    with respx.mock:
        ruta = respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(401, json={"error": "invalid API key"})
        )
        with pytest.raises(TokenInvalido):
            await cliente.validar_token()

    assert ruta.call_count == 1, "un 401 no se reintenta"


async def test_reintenta_ante_429_y_al_final_avisa(cliente: ClienteBallchasing) -> None:
    with respx.mock:
        ruta = respx.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(429, json={"error": "Too many requests"})
        )
        with pytest.raises(CuotaAgotada):
            await cliente.validar_token()

    assert ruta.call_count == 4, "debe agotar los 4 intentos antes de rendirse"


async def test_429_seguido_de_200_recupera(cliente: ClienteBallchasing) -> None:
    with respx.mock:
        respx.get(f"{BASE}/replays").mock(
            side_effect=[
                httpx.Response(429, json={"error": "Too many requests"}),
                httpx.Response(200, json={"list": [{"id": "ok"}]}),
            ]
        )
        datos = await cliente.validar_token()

    assert datos["ok"] is True


async def test_500_se_reintenta(cliente: ClienteBallchasing) -> None:
    with respx.mock:
        respx.get(f"{BASE}/replays").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json={"list": []}),
            ]
        )
        datos = await cliente.validar_token()

    assert datos["ok"] is True


async def test_error_de_red_no_rompe(cliente: ClienteBallchasing) -> None:
    with respx.mock:
        respx.get(f"{BASE}/replays").mock(side_effect=httpx.ConnectError("sin red"))
        with pytest.raises(ErrorBallchasing, match="Fallo de red"):
            await cliente.validar_token()


async def test_json_invalido_da_error_explicito(cliente: ClienteBallchasing) -> None:
    with respx.mock:
        respx.get(f"{BASE}/replays").mock(return_value=httpx.Response(200, text="no soy json"))
        with pytest.raises(ErrorBallchasing, match="JSON"):
            await cliente.listar_replays(limit=1)


async def test_el_token_no_aparece_en_los_logs(cliente: ClienteBallchasing) -> None:
    """El cliente registra rutas y estados, nunca la cabecera de autorizacion."""
    with respx.mock:
        respx.get(f"{BASE}/replays").mock(return_value=httpx.Response(401, json={}))
        with pytest.raises(TokenInvalido):
            await cliente.validar_token()

    rutas = [ruta for _marca, ruta, _estado in cliente.registro.eventos]
    assert rutas == ["/replays"]


async def test_el_token_se_manda_sin_bearer() -> None:
    """La API real no acepta `Bearer`: es solo el token."""
    async with httpx.AsyncClient(base_url=BASE) as http:
        cliente = ClienteBallchasing("token-secreto", cliente_http=http, max_intentos=1)
        with respx.mock:
            ruta = respx.get(f"{BASE}/replays").mock(
                return_value=httpx.Response(200, json={"list": []})
            )
            await cliente.listar_replays(limit=1)

    assert ruta.calls.last.request.headers["Authorization"] == "token-secreto"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("  token  ", "token"),
        ("Bearer token", "token"),
        ("bearer token", "token"),
    ],
)
def test_normalizar_token(entrada: str, esperado: str) -> None:
    assert validar_formato_de_token(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "   ", "x" * 513])
def test_normalizar_token_rechaza_lo_invalido(entrada: str) -> None:
    with pytest.raises(ValueError, match="token"):
        validar_formato_de_token(entrada)


# --- limitador de peticiones ---


def test_la_bolsa_arranca_llena_y_se_vacia() -> None:
    bolsa = BolsaDeTokens(capacidad=2, por_segundo=1)

    assert bolsa.consumir() is True
    assert bolsa.consumir() is True
    assert bolsa.consumir() is False


def test_la_bolsa_calcula_la_espera() -> None:
    bolsa = BolsaDeTokens(capacidad=1, por_segundo=1)
    bolsa.consumir()

    # Queda ~1 token por segundo: hay que esperar cerca de 1s.
    assert 0 < bolsa.segundos_hasta_tener() <= 1.0


def test_la_bolsa_no_crece_mas_alla_de_la_capacidad() -> None:
    bolsa = BolsaDeTokens(capacidad=2, por_segundo=1000)

    # Estando parada, no debe acumular infinitos tokens.
    assert bolsa.tokens <= 2


def test_limitador_avisa_cuando_no_hay_cupo() -> None:
    limitador = LimitadorDePeticiones(por_segundo=1, por_hora=1, por_dia=1)
    assert limitador.hay_cupo() is True

    limitador.esperar()  # consume el token de segundo, hora y dia

    assert limitador.hay_cupo() is False


def test_el_limite_por_segundo_es_el_que_manda() -> None:
    """Con cuota de hora agotada, el limite por segundo no debe despertarla."""
    limitador = LimitadorDePeticiones(por_segundo=2, por_hora=1, por_dia=1)
    limitador.esperar()

    # La bolsa de segundo se repone, la de hora no.
    assert limitador.bolsas[0].hay_cupo() is True
    assert limitador.bolsas[1].hay_cupo() is False
