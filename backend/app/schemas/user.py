"""Esquemas de usuario."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserProfile(BaseModel):
    """Perfil publico del usuario."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    display_name: str | None
    created_at: datetime = Field(description="Momento de alta en el servicio.")
