"""Esquemas de cuentas de juego."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GameAccountEntrada(BaseModel):
    """Datos de una cuenta de juego."""

    platform: str = Field(
        max_length=16, examples=["steam"], description="steam, epic, psn, switch, xbox..."
    )
    platform_id: str = Field(
        max_length=64,
        examples=["76561199085282414"],
        description="Identificador de la cuenta en esa plataforma.",
    )
    display_name: str | None = Field(default=None, max_length=64)


class GameAccountSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: str
    platform_id: str
    display_name: str | None
    created_at: datetime
