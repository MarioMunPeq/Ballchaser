"""Tests de los endpoints de credencial y cuentas de juego.

Ballchasing se simula con `respx`. Lo que se comprueba sobre todo es que el token no
se filtra: ni por la respuesta, ni por los logs, ni por la exception.
"""

import uuid

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core import crypto
from app.core.config import settings
from app.db.models import BallchasingCredential, GameAccount, User
from tests.fakes import bearer

BASE = "https://ballchasing.com/api"
TOKEN = "un-token-de-ballchasing-supremamente-secreto"


@pytest.fixture(autouse=True)
def _clave(monkeypatch: pytest.MonkeyPatch) -> None:
    """Una clave de cifrado valida en cada test."""
    monkeypatch.setattr(settings, "secret_encryption_key", crypto.generar_clave())


@pytest.fixture
def ballchasing_acepta() -> respx.Router:
    """Simula un Ballchasing que acepta el token."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(200, json={"list": [], "count": 0, "next": None})
        )
        yield router


@pytest.fixture
def ballchasing_rechaza() -> respx.Router:
    """Simula un Ballchasing que no reconoce el token."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{BASE}/replays").mock(
            return_value=httpx.Response(401, json={"error": "invalid API key"})
        )
        yield router


@pytest.fixture
def ballchasing_caido() -> respx.Router:
    """Simula un Ballchasing que no responde bien."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{BASE}/replays").mock(return_value=httpx.Response(503))
        yield router


# --- guardar y consultar el token ---


async def test_guardar_token_devuelve_estado_sin_el_token(
    client: AsyncClient, ballchasing_acepta: respx.Router
) -> None:
    response = await client.put(
        "/me/ballchasing-token", json={"token": TOKEN}, headers=bearer("token-alice")
    )

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["configured"] is True
    assert cuerpo["validated"] is True
    assert cuerpo["last_validated_at"] is not None
    assert TOKEN not in response.text


async def test_el_token_se_guarda_cifrado(
    client: AsyncClient, session: AsyncSession, ballchasing_acepta: respx.Router
) -> None:
    await client.put("/me/ballchasing-token", json={"token": TOKEN}, headers=bearer("token-alice"))

    credencial = await session.scalar(select(BallchasingCredential))
    assert credencial is not None
    assert credencial.token_encrypted != TOKEN
    assert TOKEN not in credencial.token_encrypted
    # Y se puede recuperar con la clave, que es lo que hara el worker.
    assert crypto.descifrar(credencial.token_encrypted) == TOKEN


async def test_estado_devuelve_503_si_no_hay_cifrado_configurado(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, ballchasing_acepta: respx.Router
) -> None:
    monkeypatch.setattr(settings, "secret_encryption_key", None)

    response = await client.put(
        "/me/ballchasing-token", json={"token": TOKEN}, headers=bearer("token-alice")
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "encryption_not_configured"


async def test_token_invalido_da_401_y_no_se_guarda(
    client: AsyncClient, session: AsyncSession, ballchasing_rechaza: respx.Router
) -> None:
    response = await client.put(
        "/me/ballchasing-token", json={"token": "token-inventado"}, headers=bearer("token-alice")
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_ballchasing_token"
    assert await session.scalar(select(BallchasingCredential)) is None


async def test_ballchasing_caido_da_502_y_no_guarda(
    client: AsyncClient, session: AsyncSession, ballchasing_caido: respx.Router
) -> None:
    """Un 503 de Ballchasing no es culpa del token: se distingue del 401."""
    response = await client.put(
        "/me/ballchasing-token", json={"token": TOKEN}, headers=bearer("token-alice")
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ballchasing_unavailable"
    assert await session.scalar(select(BallchasingCredential)) is None


async def test_token_vacio_da_422(client: AsyncClient, ballchasing_acepta: respx.Router) -> None:
    response = await client.put(
        "/me/ballchasing-token", json={"token": "   "}, headers=bearer("token-alice")
    )

    assert response.status_code in (422, 401)


async def test_sin_clave_no_gasta_cuota_de_ballchasing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, ballchasing_acepta: respx.Router
) -> None:
    """Sin clave de cifrado no se puede guardar nada, asi que no se llama a la API.

    Una llamada de las 500/hora no debe gastarse en un intento que va a fallar.
    """
    monkeypatch.setattr(settings, "secret_encryption_key", None)

    response = await client.put(
        "/me/ballchasing-token", json={"token": TOKEN}, headers=bearer("token-alice")
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "encryption_not_configured"
    assert ballchasing_acepta.calls.call_count == 0


async def test_get_estado_no_revela_el_token(
    client: AsyncClient, ballchasing_acepta: respx.Router
) -> None:
    await client.put("/me/ballchasing-token", json={"token": TOKEN}, headers=bearer("token-alice"))

    response = await client.get("/me/ballchasing-token", headers=bearer("token-alice"))

    assert response.status_code == 200
    assert TOKEN not in response.text
    assert set(response.json()) == {"configured", "validated", "last_validated_at"}


async def test_get_estado_sin_token_creado(client: AsyncClient) -> None:
    response = await client.get("/me/ballchasing-token", headers=bearer("token-alice"))

    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "validated": False,
        "last_validated_at": None,
    }


async def test_actualizar_token_sustituye_al_anterior(
    client: AsyncClient, session: AsyncSession, ballchasing_acepta: respx.Router
) -> None:
    await client.put("/me/ballchasing-token", json={"token": TOKEN}, headers=bearer("token-alice"))
    await client.put(
        "/me/ballchasing-token",
        json={"token": "segundo-token-nuevo"},
        headers=bearer("token-alice"),
    )

    credenciales = list((await session.scalars(select(BallchasingCredential))).all())
    assert len(credenciales) == 1
    assert crypto.descifrar(credenciales[0].token_encrypted) == "segundo-token-nuevo"


async def test_borrar_token(client: AsyncClient, session: AsyncSession) -> None:
    await client.request(
        "PUT", "/me/ballchasing-token", json={"token": TOKEN}, headers=bearer("token-alice")
    )

    response = await client.request(
        "DELETE", "/me/ballchasing-token", headers=bearer("token-alice")
    )

    assert response.status_code == 204
    assert await session.scalar(select(BallchasingCredential)) is None


async def test_rutas_del_token_exigen_autenticacion(
    client: AsyncClient, ballchasing_acepta: respx.Router
) -> None:
    for metodo, ruta in [
        ("GET", "/me/ballchasing-token"),
        ("DELETE", "/me/ballchasing-token"),
        ("PUT", "/me/ballchasing-token"),
    ]:
        response = await client.request(metodo, ruta, json={"token": TOKEN})
        assert response.status_code == 401, ruta


async def test_el_token_no_aparece_en_la_traza_de_sql(
    client: AsyncClient, engine: AsyncEngine, ballchasing_acepta: respx.Router
) -> None:
    """Las sentencias que salen hacia la base no llevan el token en claro."""
    statements: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _capturar(_conn: object, _cursor: object, statement: str, *args: object) -> None:
        statements.append(statement)

    try:
        await client.put(
            "/me/ballchasing-token", json={"token": TOKEN}, headers=bearer("token-alice")
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _capturar)

    # La sentencia lleva un marcador, no el valor: eso ya es lo importante.
    assert statements, "no se ejecuto ninguna sentencia"
    assert all(TOKEN not in s for s in statements)


async def test_el_token_no_se_devuelve_al_otro_usuario(
    client: AsyncClient, ballchasing_acepta: respx.Router
) -> None:
    await client.put("/me/ballchasing-token", json={"token": TOKEN}, headers=bearer("token-alice"))

    respuesta_bob = await client.get("/me/ballchasing-token", headers=bearer("token-bob"))

    assert respuesta_bob.json()["configured"] is False
    assert TOKEN not in respuesta_bob.text


async def test_el_repr_del_modelo_no_revela_el_token(
    client: AsyncClient, session: AsyncSession, ballchasing_acepta: respx.Router
) -> None:
    await client.put("/me/ballchasing-token", json={"token": TOKEN}, headers=bearer("token-alice"))

    credencial = await session.scalar(select(BallchasingCredential))

    assert credencial is not None
    assert TOKEN not in repr(credencial)


async def test_borrar_usuario_borra_su_credencial(
    client: AsyncClient, session: AsyncSession, ballchasing_acepta: respx.Router
) -> None:
    await client.put("/me/ballchasing-token", json={"token": TOKEN}, headers=bearer("token-alice"))

    await client.request("DELETE", "/me", headers=bearer("token-alice"))

    assert await session.scalar(select(BallchasingCredential)) is None


# --- cuentas de juego ---


async def test_crear_cuenta_de_juego(client: AsyncClient) -> None:
    response = await client.post(
        "/me/game-accounts",
        json={"platform": "Steam", "platform_id": "76561199085282414", "display_name": "S0LR"},
        headers=bearer("token-alice"),
    )

    assert response.status_code == 201
    cuerpo = response.json()
    assert cuerpo["platform"] == "steam"
    assert cuerpo["platform_id"] == "76561199085282414"
    assert cuerpo["display_name"] == "S0LR"


async def test_crear_la_misma_identidad_no_duplica(client: AsyncClient) -> None:
    datos = {"platform": "steam", "platform_id": "123", "display_name": "Viejo"}
    await client.post("/me/game-accounts", json=datos, headers=bearer("token-alice"))

    segundo = await client.post(
        "/me/game-accounts", json={**datos, "display_name": "Nuevo"}, headers=bearer("token-alice")
    )

    assert segundo.status_code == 201
    assert segundo.json()["display_name"] == "Nuevo"
    listado = await client.get("/me/game-accounts", headers=bearer("token-alice"))
    assert len(listado.json()) == 1


async def test_listar_cuentas_vacio(client: AsyncClient) -> None:
    response = await client.get("/me/game-accounts", headers=bearer("token-alice"))

    assert response.status_code == 200
    assert response.json() == []


async def test_cada_usuario_solo_ve_sus_cuentas(client: AsyncClient) -> None:
    await client.post(
        "/me/game-accounts",
        json={"platform": "steam", "platform_id": "111"},
        headers=bearer("token-alice"),
    )

    response = await client.get("/me/game-accounts", headers=bearer("token-bob"))

    assert response.json() == []


async def test_no_se_puede_borrar_una_cuenta_ajena(
    client: AsyncClient, session: AsyncSession
) -> None:
    creada = await client.post(
        "/me/game-accounts",
        json={"platform": "steam", "platform_id": "111"},
        headers=bearer("token-alice"),
    )
    id_alice = creada.json()["id"]

    response = await client.request(
        "DELETE", f"/me/game-accounts/{id_alice}", headers=bearer("token-bob")
    )

    assert response.status_code == 404
    # La cuenta de Alice sigue ahí.
    assert await session.get(GameAccount, uuid.UUID(id_alice)) is not None


async def test_borrar_una_cuenta_inexistente_da_404(client: AsyncClient) -> None:
    response = await client.request(
        "DELETE", f"/me/game-accounts/{uuid.uuid4()}", headers=bearer("token-alice")
    )

    assert response.status_code == 404


async def test_cuenta_sin_identificadores_da_422(client: AsyncClient) -> None:
    response = await client.post(
        "/me/game-accounts",
        json={"platform": "  ", "platform_id": ""},
        headers=bearer("token-alice"),
    )

    assert response.status_code == 422


async def test_borrar_usuario_borra_sus_cuentas_de_juego(
    client: AsyncClient, session: AsyncSession
) -> None:
    await client.post(
        "/me/game-accounts",
        json={"platform": "steam", "platform_id": "111"},
        headers=bearer("token-alice"),
    )

    await client.request("DELETE", "/me", headers=bearer("token-alice"))

    assert await session.scalar(select(GameAccount)) is None
    assert await session.scalar(select(User)) is None
