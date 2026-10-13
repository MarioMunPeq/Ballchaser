"""Endpoints de usuario.

Todas las rutas cuelgan de `prefix="/me"` y toman el usuario del ID token, no del
cuerpo de la peticion.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentIdentity
from app.db.session import get_session
from app.schemas.user import UserProfile
from app.services import users

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=UserProfile, summary="Perfil del usuario autenticado")
async def read_me(identity: CurrentIdentity, session: SessionDep) -> UserProfile:
    """Devuelve el perfil y da de alta al usuario la primera vez que se llama."""
    user, _created = await users.get_or_create_user(session, identity)
    return UserProfile.model_validate(user)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, summary="Borrar la cuenta")
async def delete_me(identity: CurrentIdentity, session: SessionDep) -> Response:
    """Borra cuenta y datos. Requiere volver a iniciar sesion despues."""
    user, _created = await users.get_or_create_user(session, identity)
    await users.delete_user(session, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
