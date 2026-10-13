"""Motor y sesion de base de datos."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def create_engine(url: str | None = None) -> AsyncEngine:
    """Crea el motor asincrono.

    `pool_pre_ping` evita conexiones rotas en entornos que escalan a cero, como
    Neon, y `pool_recycle` evita que el pool mantenga conexiones que el servidor ya
    cerro.
    """
    return create_async_engine(
        url or settings.database_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=False,
    )


engine = create_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependencia de FastAPI que abre una sesion por peticion."""
    async with SessionLocal() as session:
        yield session
