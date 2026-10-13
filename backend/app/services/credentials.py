"""Servicio de credenciales de Ballchasing.

El token entra por la API en claro (el usuario lo escribe), se valida contra Ballchasing
para no guardar un token roto, y se guarda **cifrado**. Nunca sale por la API ni se
registra en los logs.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.config import settings
from app.core.errors import AppError
from app.db.models.credential import BallchasingCredential
from app.services.ballchasing import ClienteBallchasing, ErrorBallchasing, TokenInvalido
from app.services.ballchasing import validar_formato_de_token as _normalizar

logger = structlog.get_logger(__name__)

PLATAFORMAS_CONOCIDAS = frozenset({"steam", "epic", "psn", "switch", "xbox"})


async def guardar_token(
    session: AsyncSession, user_id: uuid.UUID, token: str
) -> BallchasingCredential:
    """Valida el token contra Ballchasing y lo guarda cifrado.

    Se valida antes de guardar: si Ballchasing lo rechaza, el usuario recibe un 401
    claro en vez de un token roto guardado que fallara mas tarde, en la sincronizacion.
    """
    try:
        limpio = _normalizar(token)
    except ValueError as exc:
        raise AppError(status_code=422, code="invalid_token", message=str(exc)) from exc

    # Se comprueba antes de llamar a Ballchasing: sin clave de cifrado no vamos a poder
    # guardar el token, y validar contra la API externa gasta una de las 500 llamadas
    # hourly del usuario sin ningun beneficio.
    if not settings.secret_encryption_key:
        raise AppError(
            status_code=503,
            code="encryption_not_configured",
            message="El cifrado de secretos no esta configurado en el servidor.",
        )

    await _validar_contra_ballchasing(limpio)

    cifrado = crypto.cifrar(limpio)
    existente = await session.get(BallchasingCredential, user_id)
    ahora = datetime.now(UTC)

    if existente is None:
        credencial = BallchasingCredential(
            user_id=user_id,
            token_encrypted=cifrado,
            key_version=settings.secret_key_version,
            last_validated_at=ahora,
        )
        session.add(credencial)
    else:
        credencial = existente
        credencial.token_encrypted = cifrado
        credencial.key_version = settings.secret_key_version
        credencial.last_validated_at = ahora

    await session.commit()
    await session.refresh(credencial)
    # Solo el user_id: el token no se escribe en el log ni en la traza de SQL.
    logger.info("credentials.guardadas", user_id=str(user_id), key_version=credencial.key_version)
    return credencial


async def _validar_contra_ballchasing(token: str) -> dict[str, Any]:
    cliente = ClienteBallchasing(token)
    try:
        return await cliente.validar_token()
    except TokenInvalido as exc:
        raise AppError(
            status_code=401,
            code="invalid_ballchasing_token",
            message="Ballchasing no reconoce ese token.",
        ) from exc
    except ErrorBallchasing as exc:
        # Si Ballchasing esta caido, no es culpa del token: se dice explicitamente.
        raise AppError(
            status_code=502,
            code="ballchasing_unavailable",
            message="No se ha podido comprobar el token con Ballchasing. Intentalo mas tarde.",
        ) from exc
    finally:
        await cliente.cerrar()


async def obtener_credencial(
    session: AsyncSession, user_id: uuid.UUID
) -> BallchasingCredential | None:
    return await session.get(BallchasingCredential, user_id)


async def estado_de_credencial(session: AsyncSession, user_id: uuid.UUID) -> dict[str, object]:
    """Informacion para el usuario. Nunca incluye el token."""
    credencial = await obtener_credencial(session, user_id)
    if credencial is None:
        return {"configured": False, "validated": False, "last_validated_at": None}

    validado = credencial.last_validated_at is not None
    return {
        "configured": True,
        "validated": validado,
        # Si la validacion fue hace mucho, el token puede haber caducado.
        "last_validated_at": credencial.last_validated_at,
    }


async def leer_token(session: AsyncSession, user_id: uuid.UUID) -> str | None:
    """Descifra el token. Solo para uso interno del worker, nunca para responder."""
    credencial = await obtener_credencial(session, user_id)
    if credencial is None:
        return None
    try:
        return crypto.descifrar(credencial.token_encrypted)
    except crypto.ErrorDeCifrado as exc:
        # Clave rotada sin migrar, o fila manipulada. Es un fallo del servidor.
        logger.error("credentials.no_descifrables", user_id=str(user_id))
        raise AppError(
            status_code=500,
            code="credential_unreadable",
            message="No se ha podido leer la credencial guardada.",
        ) from exc


async def borrar_credencial(session: AsyncSession, user_id: uuid.UUID) -> bool:
    resultado = await session.execute(
        delete(BallchasingCredential).where(BallchasingCredential.user_id == user_id)
    )
    await session.commit()
    return bool(resultado.rowcount)  # type: ignore[attr-defined]


async def marcar_como_validada(session: AsyncSession, user_id: uuid.UUID) -> None:
    credencial = await session.scalar(
        select(BallchasingCredential).where(BallchasingCredential.user_id == user_id)
    )
    if credencial is None:
        return
    credencial.last_validated_at = datetime.now(UTC)
    await session.commit()
