"""Esquemas de la credencial de Ballchasing."""

from datetime import datetime

from pydantic import BaseModel, Field


class BallchasingTokenEntrada(BaseModel):
    """Token que escribe el usuario.

    Se acepta con o sin el prefijo `Bearer ` por comodidad, aunque la API real no lo
    usa. `repr=False` evita que el token aparezca en un volcado de Depurar.
    """

    token: str = Field(min_length=1, max_length=512, repr=False)


class BallchasingTokenEstado(BaseModel):
    """Estado de la credencial. No incluye el token en ningun caso."""

    configured: bool = Field(description="Si el usuario ha guardado un token.")
    validated: bool = Field(description="Si ese token se ha validado contra Ballchasing.")
    last_validated_at: datetime | None = Field(
        default=None, description="Ultima validacion contra Ballchasing."
    )
