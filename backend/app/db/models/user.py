"""Modelo de usuario."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UtcDateTime


class User(Base):
    """Usuario identificado por su `firebase_uid`.

    Firebase Authentication guarda la identidad y las contrasenas; aqui solo se
    guarda lo que la aplicacion necesita para funcionando.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # `unique=True` ya crea un indice en Postgres: añadir `index=True` seria un
    # indice redundante.
    firebase_uid: Mapped[str] = mapped_column(String(128), unique=True)
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        # Default en Python (el ORM lo rellena siempre) y en servidor para las
        # filas que cree SQL. `CURRENT_TIMESTAMP` existe en Postgres y en SQLite;
        # `now()` solo en Postgres.
        default=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<User {self.firebase_uid} {self.email}>"
