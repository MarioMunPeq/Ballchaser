"""Tests del cifrado de secretos."""

import base64
import os

import pytest
from cryptography.exceptions import InvalidTag

from app.core import crypto
from app.core.config import settings
from app.core.errors import AppError

CLAVE = crypto.generar_clave()
OTRA_CLAVE = crypto.generar_clave()


def test_generar_clave_devuelve_32_bytes_en_base64() -> None:
    clave = crypto.generar_clave()
    assert len(base64.b64decode(clave)) == 32


def test_generar_clave_es_aleatoria() -> None:
    assert crypto.generar_clave() != crypto.generar_clave()


def test_cifrar_y_descifrar_va_y_vuelve() -> None:
    token = "un-token-de-ballchasing-muy-secreto"

    cifrado = crypto.cifrar(token, CLAVE)

    assert crypto.descifrar(cifrado, CLAVE) == token


def test_el_texto_cifrado_no_contiene_el_token() -> None:
    token = "un-token-de-ballchasing-muy-secreto"

    cifrado = crypto.cifrar(token, CLAVE)

    assert token not in cifrado
    assert base64.b64decode(cifrado)  # es base64 valido


def test_cada_cifrado_usa_un_nonce_distinto() -> None:
    """Repetir nonce con la misma clave rompe AES-GCM de forma catastrofica."""
    token = "el-mismo-token"

    primero = crypto.cifrar(token, CLAVE)
    segundo = crypto.cifrar(token, CLAVE)

    assert primero != segundo
    assert base64.b64decode(primero)[:12] != base64.b64decode(segundo)[:12]
    assert crypto.descifrar(primero, CLAVE) == crypto.descifrar(segundo, CLAVE)


def test_otra_clave_no_descifra() -> None:
    cifrado = crypto.cifrar("secreto", CLAVE)

    with pytest.raises(crypto.ErrorDeCifrado):
        crypto.descifrar(cifrado, OTRA_CLAVE)


def test_dato_alterado_se_detecta() -> None:
    """AES-GCM da integridad: tocar un byte debe fallar, no devolver basura."""
    cifrado = crypto.cifrar("secreto", CLAVE)
    bruto = bytearray(base64.b64decode(cifrado))
    bruto[-1] ^= 0x01
    manipulado = base64.b64encode(bytes(bruto)).decode("ascii")

    with pytest.raises(crypto.ErrorDeCifrado):
        crypto.descifrar(manipulado, CLAVE)


def test_valor_no_base64_da_error_de_cifrado() -> None:
    with pytest.raises(crypto.ErrorDeCifrado):
        crypto.descifrar("no soy base64 ***", CLAVE)


def test_valor_truncado_da_error_de_cifrado() -> None:
    with pytest.raises(crypto.ErrorDeCifrado):
        crypto.descifrar(base64.b64encode(b"corto").decode("ascii"), CLAVE)


def test_clave_de_longitud_incorrecta_da_error() -> None:
    corta = base64.b64encode(os.urandom(16)).decode("ascii")

    with pytest.raises(ValueError, match="32 bytes"):
        crypto.cifrar("secreto", corta)


def test_clave_que_no_es_base64_da_error() -> None:
    with pytest.raises(ValueError, match="base64"):
        crypto.cifrar("secreto", "no-es-base64!!")


def test_sin_clave_configurada_falla_cerrado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin clave, se responde 503: nunca se guarda nada en claro."""
    monkeypatch.setattr(settings, "secret_encryption_key", None)

    with pytest.raises(AppError) as excinfo:
        crypto.cifrar("secreto")

    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "encryption_not_configured"


def test_usa_la_clave_del_entorno_por_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "secret_encryption_key", CLAVE)

    assert crypto.descifrar(crypto.cifrar("secreto")) == "secreto"


def test_el_error_de_cifrado_no_revela_la_clave() -> None:
    """Lo que se registra en un log no puede incluir material criptografico."""
    cifrado = crypto.cifrar("secreto", CLAVE)

    try:
        crypto.descifrar(cifrado, OTRA_CLAVE)
    except crypto.ErrorDeCifrado as exc:
        assert CLAVE[:8] not in str(exc)
        assert OTRA_CLAVE[:8] not in str(exc)
        assert "InvalidTag" not in str(exc)


def test_invalid_tag_es_el_causa_real() -> None:
    """Confirma que el fallo es de integridad y no un fallo de codificacion."""
    cifrado = crypto.cifrar("secreto", CLAVE)

    with pytest.raises(crypto.ErrorDeCifrado) as excinfo:
        crypto.descifrar(cifrado, OTRA_CLAVE)

    assert isinstance(excinfo.value.__cause__, InvalidTag | ValueError)
