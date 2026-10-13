"""Cifrado de secretos con AES-GCM.

El token de Ballchasing es una credencial con acceso a la cuenta del usuario, asi que
en la base de datos solo vive cifrada. Se usa AES-GCM porque ademas de confidencialidad
da integridad: si alguien altera un byte del texto cifrado, el descifrado falla en vez
de devolver basura.

Formato almacenado: `nonce || ciphertext || tag`, codificado en base64. El nonce (12 bytes)
se genera al azar en cada cifrado, nunca se reutiliza con la misma clave.
"""

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.core.errors import AppError

NONCE_BYTES = 12
CLAVE_BYTES = 32


class ErrorDeCifrado(Exception):
    """El texto cifrado no se puede descifrar con la clave indicada."""


def generar_clave() -> str:
    """Genera una clave de 32 bytes en base64, para escribir en el entorno."""
    return base64.b64encode(AESGCM.generate_key(bit_length=CLAVE_BYTES * 8)).decode("ascii")


def _decodificar_clave(clave_base64: str) -> bytes:
    try:
        clave = base64.b64decode(clave_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("La clave no es base64 valido.") from exc
    if len(clave) != CLAVE_BYTES:
        raise ValueError(f"La clave debe tener {CLAVE_BYTES} bytes, tiene {len(clave)}.")
    return clave


def cifrar(texto: str, clave_base64: str | None = None) -> str:
    """Cifra `texto` y devuelve base64 de `nonce || ciphertext || tag`."""
    clave = _decodificar_clave(clave_base64 or _clave_obligatoria())
    cifrador = AESGCM(clave)
    nonce = os.urandom(NONCE_BYTES)
    return base64.b64encode(nonce + cifrador.encrypt(nonce, texto.encode("utf-8"), None)).decode(
        "ascii"
    )


def descifrar(datos_base64: str, clave_base64: str | None = None) -> str:
    """Deshace `cifrar`. Lanza `ErrorDeCifrado` si el texto fue alterado."""
    clave = _decodificar_clave(clave_base64 or _clave_obligatoria())
    try:
        bruto = base64.b64decode(datos_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ErrorDeCifrado("El valor cifrado no es base64 valido.") from exc

    if len(bruto) <= NONCE_BYTES:
        raise ErrorDeCifrado("El valor cifrado esta truncado.")

    nonce, cuerpo = bruto[:NONCE_BYTES], bruto[NONCE_BYTES:]
    try:
        return AESGCM(clave).decrypt(nonce, cuerpo, None).decode("utf-8")
    except (InvalidTag, UnicodeDecodeError) as exc:
        raise ErrorDeCifrado("No se puede descifrar: clave incorrecta o dato alterado.") from exc


def _clave_obligatoria() -> str:
    clave = settings.secret_encryption_key
    if not clave:
        # Fallo cerrado: es preferible un 503 a guardar un token en claro.
        raise AppError(
            status_code=503,
            code="encryption_not_configured",
            message="El cifrado de secretos no esta configurado en el servidor.",
        )
    return clave
