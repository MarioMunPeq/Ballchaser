"""Tests de /me: alta, perfil y borrado."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from tests.fakes import bearer, make_token


async def test_me_crea_el_usuario_en_la_primera_llamada(client: AsyncClient) -> None:
    response = await client.get("/me", headers=bearer("token-alice"))

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert body["display_name"] == "Alice"
    assert body["id"]
    assert body["created_at"]


async def test_me_no_duplica_al_usuario(client: AsyncClient, session: AsyncSession) -> None:
    primera = await client.get("/me", headers=bearer("token-alice"))
    segunda = await client.get("/me", headers=bearer("token-alice"))

    assert primera.json()["id"] == segunda.json()["id"]
    assert segunda.json()["created_at"] == primera.json()["created_at"]

    total = await session.scalar(select(func.count()).select_from(User))
    assert total == 1


async def test_me_acepta_usuarios_sin_email(
    client: AsyncClient,
) -> None:
    response = await client.get("/me", headers=bearer("token-sin-email"))

    assert response.status_code == 200
    assert response.json()["email"] is None


async def test_me_actualiza_el_perfil_cuando_cambia_el_nombre(
    client: AsyncClient, verifier: object
) -> None:
    await client.get("/me", headers=bearer("token-alice"))

    token = make_token(
        "uid-alice", verifier, email="alice@example.com", display_name="Alice Renombrada"
    )
    response = await client.get("/me", headers=bearer(token))

    assert response.json()["display_name"] == "Alice Renombrada"


async def test_delete_me_borra_la_cuenta(client: AsyncClient, session: AsyncSession) -> None:
    await client.get("/me", headers=bearer("token-alice"))

    response = await client.request("DELETE", "/me", headers=bearer("token-alice"))

    assert response.status_code == 204
    assert response.content == b""

    restantes = await session.scalar(select(func.count()).select_from(User))
    assert restantes == 0


async def test_tras_borrar_la_cuenta_se_crea_de_nuevo(client: AsyncClient) -> None:
    await client.get("/me", headers=bearer("token-alice"))
    await client.request("DELETE", "/me", headers=bearer("token-alice"))

    response = await client.get("/me", headers=bearer("token-alice"))

    assert response.status_code == 200


async def test_cada_usuario_solo_ve_su_perfil(client: AsyncClient) -> None:
    alice = await client.get("/me", headers=bearer("token-alice"))
    bob = await client.get("/me", headers=bearer("token-bob"))

    assert alice.json()["id"] != bob.json()["id"]
    assert alice.json()["email"] == "alice@example.com"
    assert bob.json()["email"] == "bob@example.com"


async def test_borrar_como_un_usuario_no_toca_a_los_demas(
    client: AsyncClient, session: AsyncSession
) -> None:
    await client.get("/me", headers=bearer("token-alice"))
    await client.get("/me", headers=bearer("token-bob"))

    await client.request("DELETE", "/me", headers=bearer("token-bob"))

    restante = await session.scalar(select(User).where(User.firebase_uid == "uid-alice"))
    assert restante is not None


async def test_delete_me_requiere_token(client: AsyncClient) -> None:
    response = await client.request("DELETE", "/me")

    assert response.status_code == 401


@pytest.mark.parametrize("metodo", ["GET", "DELETE"])
async def test_rutas_de_usuario_no_exponen_el_uid_de_otros(
    client: AsyncClient, metodo: str
) -> None:
    await client.get("/me", headers=bearer("token-bob"))

    respuesta = await client.request(metodo, "/me", headers=bearer("token-alice"))

    # DELETE devuelve 204 sin cuerpo; GET devuelve el perfil del propio usuario.
    cuerpo = respuesta.text
    assert "uid-bob" not in cuerpo
    assert "bob@example.com" not in cuerpo
