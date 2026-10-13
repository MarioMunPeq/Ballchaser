"""Tests de la verificacion de ID tokens."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import _init_firebase_app, get_identity_verifier
from tests.fakes import bearer


async def test_ruta_protegida_sin_token_devuelve_401(client: AsyncClient) -> None:
    response = await client.get("/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_ruta_protegida_con_token_invalido_devuelve_401(client: AsyncClient) -> None:
    response = await client.get("/me", headers=bearer("token-fabricado"))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_esquema_distinto_a_bearer_devuelve_401(client: AsyncClient) -> None:
    response = await client.get("/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})

    assert response.status_code == 401


async def test_401_incluye_www_authenticate(client: AsyncClient) -> None:
    response = await client.get("/me")

    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_token_valido_llega_al_verificador(client: AsyncClient, verifier: object) -> None:
    response = await client.get("/me", headers=bearer("token-alice"))

    assert response.status_code == 200
    assert "token-alice" in verifier.seen_tokens


async def test_health_es_publico(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200


async def test_sin_credenciales_de_firebase_el_servidor_falla_cerrado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "firebase_credentials_json", None)

    with pytest.raises(AppError) as excinfo:
        _init_firebase_app()

    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "auth_not_configured"


async def test_sin_configuracion_una_peticion_sin_token_sigue_dando_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El 401 va antes que el 503: primero se exige el token, luego se verifica."""
    monkeypatch.setattr(settings, "firebase_credentials_json", None)

    response = await client.get("/me")

    assert response.status_code == 401


async def test_sin_configuracion_un_token_presenta_da_503(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con un token en mano pero sin credenciales, el error es de configuracion."""
    monkeypatch.setattr(settings, "firebase_credentials_json", None)
    app.dependency_overrides.pop(get_identity_verifier, None)

    response = await client.get("/me", headers=bearer("token-alice"))

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "auth_not_configured"


async def test_credenciales_de_firebase_invalidas_fallan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "firebase_credentials_json", "{no es json")

    with pytest.raises(AppError) as excinfo:
        _init_firebase_app()

    assert excinfo.value.code == "auth_not_configured"
