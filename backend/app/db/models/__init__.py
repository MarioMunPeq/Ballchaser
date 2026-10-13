"""Modelos de la base de datos."""

from app.db.base import Base
from app.db.models.user import User

__all__ = ["Base", "User"]
