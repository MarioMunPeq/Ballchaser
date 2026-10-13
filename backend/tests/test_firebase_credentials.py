"""Tests de la carga de credenciales de Firebase."""

import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import _init_firebase_app, get_identity_verifier
from tests.fakes import bearer

CREDENCIAL_FALSA: dict[str, Any] = {
    "type": "service_account",
    "project_id": "ballchaser-demo",
    "private_key_id": "abc",
    # No es una clave valida: aqui solo importa que se lea el fichero y se
    # detecte que el PEM no sirve para nada.
    "private_key": "-----BEGIN PRIVATE KEY-----\nno-es-una-clave\n-----END PRIVATE KEY-----\n",
    "client_email": "firebase-adminsdk-abc@ballchaser-demo.iam.gserviceaccount.com",
    "client_id": "1234567890",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/demo",
}


def credencial_valida() -> dict[str, Any]:
    """Credencial con una clave RSA de verdad, generada en memoria."""
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = clave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return {**CREDENCIAL_FALSA, "private_key": pem, "private_key_id": "clave-de-prueba"}


def _escribir(credencial: dict[str, Any], tmp_path: Path) -> Path:
    ruta = tmp_path / "firebase-service-account.json"
    ruta.write_text(json.dumps(credencial), encoding="utf-8")
    return ruta


def test_credenciales_desde_fichero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ruta = _escribir(credencial_valida(), tmp_path)
    monkeypatch.setattr(settings, "firebase_credentials_file", str(ruta))

    firebase_app = _init_firebase_app()

    assert firebase_app.project_id == "ballchaser-demo"


def test_credenciales_desde_variable_de_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "firebase_credentials_file", None)
    monkeypatch.setattr(settings, "firebase_credentials_json", json.dumps(credencial_valida()))

    assert _init_firebase_app().project_id == "ballchaser-demo"


def test_pem_corrupto_es_error_de_configuracion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ruta = _escribir(CREDENCIAL_FALSA, tmp_path)
    monkeypatch.setattr(settings, "firebase_credentials_file", str(ruta))

    with pytest.raises(AppError) as excinfo:
        _init_firebase_app()

    assert excinfo.value.code == "auth_not_configured"
    assert excinfo.value.status_code == 503


def test_fichero_inexistente_es_error_de_configuracion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "firebase_credentials_file", str(tmp_path / "no-existe.json"))

    with pytest.raises(AppError) as excinfo:
        _init_firebase_app()

    assert excinfo.value.code == "auth_not_configured"


def test_json_invalido_es_error_de_configuracion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "firebase_credentials_json", "{esto no es json")

    with pytest.raises(AppError) as excinfo:
        _init_firebase_app()

    assert excinfo.value.code == "auth_not_configured"


async def test_un_token_falso_no_pasa_con_credenciales_cargadas(
    client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Con credenciales cargadas, un token inventado es un 401, no un 503."""
    ruta = _escribir(credencial_valida(), tmp_path)
    monkeypatch.setattr(settings, "firebase_credentials_file", str(ruta))
    app.dependency_overrides.pop(get_identity_verifier, None)

    response = await client.get("/me", headers=bearer("token-inventado"))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
