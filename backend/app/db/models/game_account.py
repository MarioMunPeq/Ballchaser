"""Cuenta de juego de un usuario.

Un mismo usuario puede tener varias cuentas (por ejemplo, Steam y PlayStation). Sirven
para saber a que jugador de cada replay pertenece su ficha.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UtcDateTime


class GameAccount(Base):
    """Vincula un usuario con una identidad de juego de una plataforma."""

    __tablename__ = "game_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "platform", "platform_id", name="uq_game_accounts_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 'steam', 'epic', 'psn', 'switch', 'xbox'...
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    platform_id: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        default=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<GameAccount {self.platform}:{self.platform_id}>"
