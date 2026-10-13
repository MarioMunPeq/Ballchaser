"""Servicio de cuentas de juego.

Las cuentas se consultan siempre filtrando por el `user_id` que viene del token de
identidad: el `user_id` del cuerpo de la peticion no existe, asi que no hay forma de
pedir cuentas ajenas.
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.game_account import GameAccount


async def listar(session: AsyncSession, user_id: uuid.UUID) -> list[GameAccount]:
    resultado = await session.execute(
        select(GameAccount).where(GameAccount.user_id == user_id).order_by(GameAccount.created_at)
    )
    return list(resultado.scalars())


async def crear(
    session: AsyncSession,
    user_id: uuid.UUID,
    platform: str,
    platform_id: str,
    display_name: str | None = None,
) -> GameAccount:
    """Crea una cuenta. Si la identidad ya existe, actualiza el nombre y la devuelve.

    Un mismo jugador reenviando sus datos no es un error: se refresca el nombre, que es
    lo unico que cambia (por ejemplo, si cambio el nombre en Steam).
    """
    platform = platform.strip().lower()
    platform_id = platform_id.strip()

    if not platform or not platform_id:
        raise AppError(
            status_code=422,
            code="invalid_game_account",
            message="Plataforma e identificador son obligatorios.",
        )

    existente = await session.scalar(
        select(GameAccount).where(
            GameAccount.user_id == user_id,
            GameAccount.platform == platform,
            GameAccount.platform_id == platform_id,
        )
    )
    if existente is not None:
        if display_name and existente.display_name != display_name:
            existente.display_name = display_name
            await session.commit()
            await session.refresh(existente)
        return existente

    cuenta = GameAccount(
        user_id=user_id,
        platform=platform,
        platform_id=platform_id,
        display_name=(display_name or None),
    )
    session.add(cuenta)
    try:
        await session.commit()
    except IntegrityError as exc:
        # Carrera: dos peticiones simultaneas con la misma identidad.
        await session.rollback()
        raise AppError(
            status_code=409,
            code="game_account_exists",
            message="Ya tienes una cuenta con esa plataforma e identificador.",
        ) from exc
    await session.refresh(cuenta)
    return cuenta


async def obtener_por_id(
    session: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID
) -> GameAccount:
    """Devuelve la cuenta solo si pertenece al usuario. Si no, 404."""
    cuenta = await session.scalar(
        select(GameAccount).where(GameAccount.id == account_id, GameAccount.user_id == user_id)
    )
    if cuenta is None:
        # 404 y no 403: no se confirma si ese id existe en la base de datos.
        raise AppError(
            status_code=404,
            code="game_account_not_found",
            message="No existe esa cuenta de juego.",
        )
    return cuenta


async def borrar(session: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID) -> None:
    await obtener_por_id(session, user_id, account_id)
    await session.execute(delete(GameAccount).where(GameAccount.id == account_id))
    await session.commit()
