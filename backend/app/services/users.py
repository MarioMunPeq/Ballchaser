"""Logica de usuario: alta bajo demanda y perfil.

La identidad la aporta Firebase; aqui solo se crea la fila local la primera vez
que un `uid` aparece y se mantienen los datos de perfil al alcance.
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Identity
from app.db.models.user import User


async def get_or_create_user(session: AsyncSession, identity: Identity) -> tuple[User, bool]:
    """Devuelve el usuario del `uid`, creandolo si es la primera vez.

    El perfil se refresca con los datos del token en cada llamada: si el usuario
    cambia su nombre o su email en Firebase, aqui se refleja sin pasos extra.
    """
    user = await session.scalar(select(User).where(User.firebase_uid == identity.uid))

    if user is None:
        user = User(
            id=uuid.uuid4(),
            firebase_uid=identity.uid,
            email=identity.email,
            display_name=identity.display_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user, True

    changed = user.email != identity.email or user.display_name != identity.display_name
    if changed:
        user.email = identity.email
        user.display_name = identity.display_name
        await session.commit()
        await session.refresh(user)

    return user, False


async def delete_user(session: AsyncSession, user: User) -> None:
    """Borra la cuenta y sus datos asociados.

    Solo se admite el `user_id` que viene de la identidad del token, nunca uno
    recibido en el cuerpo de la peticion.
    """
    await session.execute(delete(User).where(User.id == user.id))
    await session.commit()
