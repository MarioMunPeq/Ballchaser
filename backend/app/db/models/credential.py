"""Credenciales de Ballchasing de un usuario.

El token da acceso a la cuenta del usuario en Ballchasing, asi que se guarda cifrado con
AES-GCM. `key_version` permite rotar la clave sin reescribir todo: al leer se usa la clave
que corresponda a esa version.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BallchasingCredential(Base):
    """Token de Ballchasing de un usuario, cifrado."""

    __tablename__ = "ballchasing_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    token_encrypted: Mapped[str] = mapped_column(String(512), nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        # Nunca el token: aqui acaba en los logs.
        return f"<BallchasingCredential user_id={self.user_id} v{self.key_version}>"
