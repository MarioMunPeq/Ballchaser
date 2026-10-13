"""Tipos de columna propios.

`DateTime(timezone=True)` no basta: Postgres devuelve datetimes con zona horaria y
SQLite los devuelve ingenuos. Con solo `timezone=True` una misma comparacion de fechas
funciona en produccion y revienta en local ("can't compare offset-naive and
offset-aware datetimes"), que es la peor forma de fallo posible.

`UtcDateTime` obliga a que todo datetime entre en UTC y salga de la base con zona
horaria, sea cual sea el motor.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """DateTime con zona horaria, siempre en UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        # Un datetime sin zona se asume en UTC: en esta aplicacion todos los
        # instantes se guardan en UTC.
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        # SQLite pierde la zona al leer; se vuelve a poner UTC.
        return value if value.tzinfo else value.replace(tzinfo=UTC)
