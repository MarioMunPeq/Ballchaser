"""Autenticacion delegada en Firebase Authentication.

El frontend inicia sesion con el SDK de Firebase y envia el ID token como
`Authorization: Bearer <jwt>`. Aqui solo se verifica la firma y se extrae la
identidad; las contrasenas nunca pasan por este servicio.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Protocol

import firebase_admin
import structlog
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

from app.core.config import settings
from app.core.errors import AppError, unauthorized

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Identity:
    """Identidad verificada extraida de un ID token de Firebase."""

    uid: str
    email: str | None
    display_name: str | None


class IdentityVerifier(Protocol):
    """Contrato que permite sustituir Firebase en los tests."""

    def verify(self, id_token: str) -> Identity: ...


class FirebaseIdentityVerifier:
    """Verifica ID tokens contra Firebase Authentication."""

    def __init__(self, client: firebase_auth.Client) -> None:
        self._client = client

    def verify(self, id_token: str) -> Identity:
        try:
            # `check_revoked` consulta si el usuario fue eliminado o sus tokens
            # revocados desde la consola de Firebase.
            claims = self._client.verify_id_token(id_token, check_revoked=True)
        except firebase_auth.ExpiredIdTokenError as exc:
            raise unauthorized("El token ha caducado.") from exc
        except firebase_auth.InvalidIdTokenError as exc:
            logger.info("auth.invalid_token", reason=str(exc))
            raise unauthorized() from exc

        uid = claims.get("uid") or claims.get("sub")
        if not uid:
            logger.warning("auth.token_without_uid")
            raise unauthorized()

        return Identity(
            uid=uid,
            email=claims.get("email"),
            display_name=claims.get("name"),
        )


def _init_firebase_app() -> firebase_admin.App:
    """Crea (o recupera) la app de firebase-admin a partir de la configuracion."""
    try:
        return firebase_admin.get_app()
    except ValueError:
        pass

    raw = settings.firebase_credentials_json
    if not raw:
        raise AppError(
            status_code=503,
            code="auth_not_configured",
            message="La autenticacion no esta configurada en el servidor.",
        )

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(
            status_code=503,
            code="auth_not_configured",
            message="FIREBASE_CREDENTIALS_JSON no es un JSON valido.",
        ) from exc

    return firebase_admin.initialize_app(credentials.Certificate(parsed))


@lru_cache
def _cached_verifier() -> FirebaseIdentityVerifier:
    """Verificador unico por proceso: firebase-admin cachea las claves publicas."""
    return FirebaseIdentityVerifier(firebase_auth.Client(_init_firebase_app()))


class LazyFirebaseIdentityVerifier:
    """Conecta con Firebase la primera vez que se verifica un token.

    Devolver una instancia perezosa en vez de el verificador ya construido
    importa: FastAPI resuelve las dependencias antes de ejecutar el endpoint, y
    si aqui fallara por falta de credenciales, una peticion sin token responderia
    503 en lugar del 401 que corresponde. Asi el 503 sale solo cuando hay un token
    que de verdad hay que verificar.
    """

    def verify(self, id_token: str) -> Identity:
        return _cached_verifier().verify(id_token)


def get_identity_verifier() -> LazyFirebaseIdentityVerifier:
    """Dependencia que expone el verificador de identidad."""
    return LazyFirebaseIdentityVerifier()


bearer_scheme = HTTPBearer(auto_error=False, description="ID token de Firebase")


async def get_current_identity(
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verifier: Annotated[IdentityVerifier, Depends(get_identity_verifier)],
) -> Identity:
    """Exige un ID token valido y devuelve la identidad correspondiente.

    El usuario sale siempre del token, nunca del cuerpo de la peticion.
    """
    if bearer is None or bearer.scheme.lower() != "bearer":
        raise unauthorized()

    return verifier.verify(bearer.credentials)


CurrentIdentity = Annotated[Identity, Depends(get_current_identity)]
