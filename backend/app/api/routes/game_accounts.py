"""Endpoints de cuentas de juego.

Todas las consultas filtran por el `user_id` del token de identidad. No hay ningun
parametro para decir de quien son los datos.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentIdentity
from app.db.session import get_session
from app.schemas.game_account import GameAccountEntrada, GameAccountSalida
from app.services import game_accounts, users

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[GameAccountSalida], summary="Listar cuentas de juego")
async def listar_cuentas(identity: CurrentIdentity, session: SessionDep) -> list[GameAccountSalida]:
    user, _created = await users.get_or_create_user(session, identity)
    cuentas = await game_accounts.listar(session, user.id)
    return [GameAccountSalida.model_validate(c) for c in cuentas]


@router.post(
    "",
    response_model=GameAccountSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Anadir una cuenta de juego",
)
async def crear_cuenta(
    cuerpo: GameAccountEntrada, identity: CurrentIdentity, session: SessionDep
) -> GameAccountSalida:
    """Crea la cuenta, o actualiza su nombre si esa identidad ya estaba."""
    user, _created = await users.get_or_create_user(session, identity)
    cuenta = await game_accounts.crear(
        session,
        user_id=user.id,
        platform=cuerpo.platform,
        platform_id=cuerpo.platform_id,
        display_name=cuerpo.display_name,
    )
    return GameAccountSalida.model_validate(cuenta)


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar una cuenta de juego",
)
async def borrar_cuenta(
    account_id: uuid.UUID, identity: CurrentIdentity, session: SessionDep
) -> Response:
    """Solo se puede borrar una cuenta propia; si no es suya, 404."""
    user, _created = await users.get_or_create_user(session, identity)
    await game_accounts.borrar(session, user_id=user.id, account_id=account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
