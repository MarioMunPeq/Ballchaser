"""Fixtures compartidas por los tests.

Los tests usan SQLite en memoria para no depender de Docker; el mismo conjunto
de pruebas corre contra Postgres definiendo `TEST_DATABASE_URL`.
"""

import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from contextlib import suppress
from pathlib import Path
from typing import Any

import firebase_admin
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine, delete, event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.security import get_identity_verifier
from app.db.models import Base
from app.db.session import get_session
from app.main import create_app
from tests.fakes import FakeIdentityVerifier

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Por defecto, un fichero SQLite temporal. No se usa `sqlite:///:memory:` porque
# Alembic abre su propia conexion (y con `:memory:` cada conexion ve una base
# distinta, asi que las migraciones se aplicarian sobre otra base vacia).
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "") or (
    f"sqlite+aiosqlite:///{Path(tempfile.gettempdir()) / 'ballchaser_tests.sqlite3'}"
)


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Cada test empieza sin configuracion heredada ni estado global de Firebase.

    Sin esto los tests dependen del `.env` del desarrollador: aqui pasarian y en
    la maquina de al lado fallarian.
    """
    monkeypatch.setattr(settings, "firebase_credentials_file", None)
    monkeypatch.setattr(settings, "firebase_credentials_json", None)
    _borrar_app_firebase()
    yield
    _borrar_app_firebase()


def _borrar_app_firebase() -> None:
    # Sin app registrada, `get_app` lanza ValueError y no hay nada que limpiar.
    with suppress(ValueError):
        firebase_admin.delete_app(firebase_admin.get_app())


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Motor de prueba con el esquema construido por las migraciones.

    Se usa Alembic y no `create_all` a proposito: si el modelo y la migracion se
    desincronizan, aqui falla el test en vez de producción. Ademas deja el esquema
    limpio al terminar, para que el siguiente test no lo herede.
    """
    test_engine = create_async_engine(TEST_DATABASE_URL)
    await _migrar(test_engine, "head")
    yield test_engine
    await _migrar(test_engine, "base")
    await test_engine.dispose()


@event.listens_for(Engine, "connect")
def _claves_foraneas_siempre(dbapi_connection: Any, record: Any) -> None:
    """Activa las claves foraneas en SQLite, en todas las conexiones del pool.

    SQLite las tiene desactivadas por defecto y el PRAGMA es por conexion: si solo se
    activa en una, el resto del pool insertaria filas huerfanas que Postgres si
    rechaza. Con `aiosqlite` lo que llega no es una `sqlite3.Connection` sino el
    adaptador de SQLAlchemy, de ahi la comprobacion por modulo.
    """
    del record
    if "sqlite" not in type(dbapi_connection).__module__:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async def _migrar(test_engine: AsyncEngine, revision: str) -> None:
    """Ejecuta `alembic upgrade/downgrade` reutilizando el motor de pruebas.

    Se pasa la conexion ya abierta en vez de dejar que Alembic cree la suya: asi
    las migraciones se aplican exactamente sobre la base que usa el test.
    """
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    comando = command.upgrade if revision != "base" else command.downgrade

    async with test_engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: _con_conexion(config, sync_conn, comando, revision))


def _con_conexion(config: Config, sync_conn: object, comando: object, revision: str) -> None:
    config.attributes["connection"] = sync_conn
    comando(config, revision)  # type: ignore[operator]
    config.attributes.pop("connection", None)


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sesion de base de datos compartida por el test, sobre datos limpios."""
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as db_session:
        yield db_session
    await _truncate_all(engine)


async def _truncate_all(engine: AsyncEngine) -> None:
    """Deja la base de datos como estaba antes del test.

    Imprescindible con Postgres: los datos sobreviven entre tests (y entre
    ejecuciones), mientras que SQLite en memoria arranca de cero cada vez. Sin
    esto los tests dependen del orden y fallan por filas de otros tests.
    """
    async with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(delete(table))
            return
        tablas = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
        await conn.execute(text(f"TRUNCATE {tablas} RESTART IDENTITY CASCADE"))


@pytest.fixture
def verifier() -> FakeIdentityVerifier:
    """Verificador de identidad con usuarios predefinidos."""
    return FakeIdentityVerifier()


@pytest.fixture
async def app(session: AsyncSession, verifier: FakeIdentityVerifier) -> AsyncIterator[FastAPI]:
    """Aplicacion con la sesion y el verificador de identidad sustituidos."""
    application = create_app()

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield session

    application.dependency_overrides[get_session] = override_get_session
    application.dependency_overrides[get_identity_verifier] = lambda: verifier
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Cliente HTTP contra la app en memoria."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
