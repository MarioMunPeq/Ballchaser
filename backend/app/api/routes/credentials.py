"""Endpoints de la credencial de Ballchasing.

`PUT` valida el token contra Ballchasing y lo guarda cifrado. `GET` solo devuelve si
esta configurado y cuando se valido: **el token no sale nunca por la API**.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentIdentity
from app.db.session import get_session
from app.schemas.ballchasing import BallchasingTokenEntrada, BallchasingTokenEstado
from app.services import credentials, users

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.put(
    "/ballchasing-token",
    response_model=BallchasingTokenEstado,
    summary="Guardar el token de Ballchasing (cifrado)",
)
async def guardar_token(
    cuerpo: BallchasingTokenEntrada, identity: CurrentIdentity, session: SessionDep
) -> BallchasingTokenEstado:
    """Valida el token contra Ballchasing y lo guarda cifrado.

    Devuelve 401 si Ballchasing no lo reconoce, para que el usuario se entere
    enseguida de que el token no vale.
    """
    user, _created = await users.get_or_create_user(session, identity)
    await credentials.guardar_token(session, user.id, cuerpo.token)
    return await _estado(session, user.id)


@router.get(
    "/ballchasing-token",
    response_model=BallchasingTokenEstado,
    summary="Estado de la credencial (nunca el token)",
)
async def estado_token(identity: CurrentIdentity, session: SessionDep) -> BallchasingTokenEstado:
    user, _created = await users.get_or_create_user(session, identity)
    return await _estado(session, user.id)


@router.delete(
    "/ballchasing-token",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar la credencial",
)
async def borrar_token(identity: CurrentIdentity, session: SessionDep) -> Response:
    user, _created = await users.get_or_create_user(session, identity)
    await credentials.borrar_credencial(session, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _estado(session: AsyncSession, user_id: uuid.UUID) -> BallchasingTokenEstado:
    datos = await credentials.estado_de_credencial(session, user_id)
    return BallchasingTokenEstado.model_validate(datos)
