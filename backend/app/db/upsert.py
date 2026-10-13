"""Ayudas de SQL que dependen del motor.

`ON CONFLICT DO NOTHING` no se escribe igual en Postgres que en SQLite, y los tests
corren en SQLite mientras produccion corre en Postgres. Aqui se esconde esa
diferencia para que la logica de ingesta no la tenga que conocer.
"""

from typing import Any

from sqlalchemy import Table, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession


async def insertar_si_no_existe(
    session: AsyncSession, tabla: Any, valores: dict[str, Any], claves_primarias: list[str]
) -> None:
    """Inserta ignorando el conflicto con las claves primarias dadas.

    Es lo que hace idempotente la ingesta: si la fila ya esta, no pasa nada y no es un
    error, solo se descarta. Acepta tanto una clase de modelo como su `__table__`.
    """
    destino = tabla if isinstance(tabla, Table) else tabla.__table__
    dialecto = session.get_bind().dialect.name

    if dialecto == "postgresql":
        await session.execute(
            pg_insert(destino)
            .values(**valores)
            .on_conflict_do_nothing(index_elements=claves_primarias)
        )
        return

    if dialecto == "sqlite":
        await session.execute(
            sqlite_insert(destino)
            .values(**valores)
            .on_conflict_do_nothing(index_elements=claves_primarias)
        )
        return

    # En un motor sin `ON CONFLICT` se inserta a pelo: la restriccion de clave
    # primaria sera la que rechace el duplicado.
    await session.execute(insert(destino).values(**valores))
