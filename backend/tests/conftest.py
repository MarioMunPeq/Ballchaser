"""Fixtures compartidas por los tests.

Los tests usan SQLite en memoria para no depender de Docker; el mismo conjunto
de pruebas corre contra Postgres definiendo `TEST_DATABASE_URL`.
"""

import os
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import get_identity_verifier
from app.db.models import Base
from app.db.session import get_session
from app.main import create_app
from tests.fakes import FakeIdentityVerifier

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def engine() -> AsyncIterator[object]:
    """Motor de prueba con las tablas creadas."""
    kwargs: dict[str, object] = {}
    if TEST_DATABASE_URL.startswith("sqlite"):
        # Una unica conexion en memoria compartida por todas las del test.
        kwargs = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}

    test_engine = create_async_engine(TEST_DATABASE_URL, **kwargs)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def session(engine: object) -> AsyncIterator[AsyncSession]:
    """Sesion de base de datos compartida por el test."""
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as db_session:
        yield db_session


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
