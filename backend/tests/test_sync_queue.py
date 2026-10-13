"""Tests de la cola de sincronizacion y del worker.

Lo importante de aqui: un 429 no es un fallo (se reprograma), un token invalido si, y
un trabajo a medias se recupera.
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.models import BallchasingCredential, GameAccount, SyncJob, User
from app.db.models.sync import EstadoJob
from app.services import sync_queue
from app.services.ballchasing import ClienteBallchasing, LimitadorDePeticiones
from app.worker.worker import Worker

STEAM_ID = "76561199000000001"
UID = uuid.UUID("44444444-4444-4444-4444-444444444444")
LISTADO = r".*/replays(\?.*)?$"
LISTADO_VACIO = {"list": [], "count": 0}


@pytest.fixture
def clave(monkeypatch: pytest.MonkeyPatch) -> str:
    from app.core.crypto import generar_clave

    valor = generar_clave()
    monkeypatch.setattr(settings, "secret_encryption_key", valor)
    return valor


@pytest.fixture
async def usuario(session: AsyncSession) -> User:
    user = User(email="cola@example.com", firebase_uid="uid-cola")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _preparar(
    session: AsyncSession, user: User, clave: str, con_cuentas: bool = True
) -> None:
    from app.core import crypto

    session.add(
        BallchasingCredential(
            user_id=user.id, token_encrypted=crypto.cifrar("token-de-prueba", clave)
        )
    )
    if con_cuentas:
        session.add(GameAccount(user_id=user.id, platform="steam", platform_id=STEAM_ID))
    await session.commit()


# --- cola ---


async def test_encolar_crea_un_trabajo(session: AsyncSession, usuario: User) -> None:
    trabajo = await sync_queue.encolar(session, usuario.id)

    assert trabajo.status == EstadoJob.QUEUED.value
    assert trabajo.attempts == 0


async def test_no_se_encolan_dos_trabajos_seguidos(session: AsyncSession, usuario: User) -> None:
    """Pulsar el boton dos veces no debe duplicar el trabajo."""
    primero = await sync_queue.encolar(session, usuario.id)
    segundo = await sync_queue.encolar(session, usuario.id)

    assert primero.id == segundo.id


async def test_hay_pendientes_detecta_el_trabajo(session: AsyncSession, usuario: User) -> None:
    assert await sync_queue.hay_pendientes(session, usuario.id) is False

    await sync_queue.encolar(session, usuario.id)

    assert await sync_queue.hay_pendientes(session, usuario.id) is True


async def test_reclamar_marca_el_trabajo_como_running(session: AsyncSession, usuario: User) -> None:
    await sync_queue.encolar(session, usuario.id)

    trabajo = await sync_queue.reclamar(session)

    assert trabajo is not None
    assert trabajo.status == EstadoJob.RUNNING.value
    assert trabajo.attempts == 1
    assert trabajo.started_at is not None


async def test_reclamar_no_devuelve_nada_si_no_hay_trabajos(session: AsyncSession) -> None:
    assert await sync_queue.reclamar(session) is None


async def test_reclamar_respeta_run_after(session: AsyncSession, usuario: User) -> None:
    """Un trabajo reprogramado para mas tarde no se toca hasta que toque."""
    await sync_queue.encolar(session, usuario.id)
    trabajo = await sync_queue.reclamar(session)
    trabajo.status = EstadoJob.QUEUED.value
    trabajo.run_after = datetime.now(UTC) + timedelta(hours=1)
    await session.commit()

    assert await sync_queue.reclamar(session) is None


async def test_devolver_abandonados_recupera_un_trabajo_atascado(
    session: AsyncSession, usuario: User
) -> None:
    """Si el proceso muere a mitad, el trabajo no puede quedarse en running para siempre."""
    await sync_queue.encolar(session, usuario.id)
    trabajo = await sync_queue.reclamar(session)
    trabajo.started_at = datetime.now(UTC) - timedelta(hours=2)
    await session.commit()

    devueltos = await sync_queue.devolver_abandonados(session)

    assert devueltos == 1
    assert (await session.get(SyncJob, trabajo.id)).status == EstadoJob.QUEUED.value


async def test_devolver_abandonados_no_toca_trabajos_recientes(
    session: AsyncSession, usuario: User
) -> None:
    await sync_queue.encolar(session, usuario.id)
    await sync_queue.reclamar(session)

    assert await sync_queue.devolver_abandonados(session) == 0


async def test_reprogramar_no_es_un_fallo(session: AsyncSession, usuario: User) -> None:
    """Un 429 vuelve a la cola con espera: no puede aparecer como error del usuario."""
    await sync_queue.encolar(session, usuario.id)
    trabajo = await sync_queue.reclamar(session)

    await sync_queue.reprogramar(session, trabajo, "Cuota agotada")

    assert trabajo.status == EstadoJob.QUEUED.value
    assert trabajo.run_after > datetime.now(UTC)
    assert trabajo.finished_at is None


async def test_la_espera_crece_con_los_intentos(session: AsyncSession, usuario: User) -> None:
    await sync_queue.encolar(session, usuario.id)
    trabajo = await sync_queue.reclamar(session)

    primera = trabajo.espera_reintento()
    trabajo.attempts = 4
    segunda = trabajo.espera_reintento()

    assert segunda > primera, "no hay que reintentar siempre igual de seguido"


async def test_fallar_cierra_el_trabajo(session: AsyncSession, usuario: User) -> None:
    await sync_queue.encolar(session, usuario.id)
    trabajo = await sync_queue.reclamar(session)

    await sync_queue.fallar(session, trabajo, ValueError("token invalido"))

    assert trabajo.status == EstadoJob.FAILED.value
    assert trabajo.finished_at is not None
    assert "token invalido" in trabajo.last_error


async def test_el_error_se_recorta_para_la_columna(session: AsyncSession, usuario: User) -> None:
    await sync_queue.encolar(session, usuario.id)
    trabajo = await sync_queue.reclamar(session)

    await sync_queue.fallar(session, trabajo, ValueError("x" * 5000))

    assert len(trabajo.last_error) <= 500


async def test_completar_actualiza_el_estado(session: AsyncSession, usuario: User) -> None:
    await sync_queue.encolar(session, usuario.id)
    trabajo = await sync_queue.reclamar(session)

    await sync_queue.completar(
        session, trabajo, nuevos=3, omitidos=7, ultima_partida=datetime(2024, 5, 1, tzinfo=UTC)
    )

    assert trabajo.status == EstadoJob.DONE.value
    assert trabajo.replays_nuevos == 3
    estado = await sync_queue.obtener_estado(session, usuario.id)
    assert estado is not None
    assert estado.last_replay_date == datetime(2024, 5, 1, tzinfo=UTC)


async def test_el_estado_se_crea_solo(session: AsyncSession, usuario: User) -> None:
    assert await sync_queue.obtener_estado(session, usuario.id) is None

    estado = await sync_queue.obtener_o_crear_estado(session, usuario.id)

    assert estado is not None
    assert estado.auto_sync is False


async def test_exigir_credencial_avisa_si_no_hay_token(
    session: AsyncSession, usuario: User
) -> None:
    from app.core.errors import AppError

    with pytest.raises(AppError) as excinfo:
        await sync_queue.exigir_credencial(session, usuario.id)

    assert excinfo.value.status_code == 409


async def test_exigir_credencial_pasa_si_hay_token(
    session: AsyncSession, usuario: User, clave: str
) -> None:
    await _preparar(session, usuario, clave)

    await sync_queue.exigir_credencial(session, usuario.id)


async def test_auto_sync_se_puede_activar(session: AsyncSession, usuario: User) -> None:
    estado = await sync_queue.actualizar_estado(session, usuario.id, auto_sync=True)

    assert estado.auto_sync is True


# --- worker ---

LISTADO_VACIO = {"list": [], "count": 0}


async def test_el_worker_sin_trabajo_no_hace_nada(session: AsyncSession) -> None:
    worker = _worker_para(session)

    assert await worker.ejecutar_un_trabajo(session) is False


async def test_el_worker_sincroniza(session: AsyncSession, usuario: User, clave: str) -> None:
    await _preparar(session, usuario, clave)
    await sync_queue.encolar(session, usuario.id)

    with respx.mock:
        respx.get(url__regex=LISTADO).mock(return_value=httpx.Response(200, json=LISTADO_VACIO))
        trabajo = await _worker_para(session).ejecutar_un_trabajo(session)

    assert trabajo is True
    trabajo_actual = await session.scalar(select(SyncJob).where(SyncJob.user_id == usuario.id))
    assert trabajo_actual.status == EstadoJob.DONE.value
    assert trabajo_actual.last_error is None


async def test_un_429_reprograma_en_vez_de_fallar(
    session: AsyncSession, usuario: User, clave: str
) -> None:
    """La diferencia clave: cuota agotada no es culpa del usuario."""
    await _preparar(session, usuario, clave)
    await sync_queue.encolar(session, usuario.id)

    with respx.mock:
        respx.get(url__regex=LISTADO).mock(
            return_value=httpx.Response(429, json={"error": "Too many requests"})
        )
        await _worker_para(session).ejecutar_un_trabajo(session)

    trabajo = await session.scalar(select(SyncJob).where(SyncJob.user_id == usuario.id))
    assert trabajo.status == EstadoJob.QUEUED.value
    assert trabajo.run_after > datetime.now(UTC)
    assert trabajo.finished_at is None


async def test_un_token_invalido_falla_el_trabajo(
    session: AsyncSession, usuario: User, clave: str
) -> None:
    await _preparar(session, usuario, clave)
    await sync_queue.encolar(session, usuario.id)

    with respx.mock:
        respx.get(url__regex=LISTADO).mock(
            return_value=httpx.Response(401, json={"error": "invalid API key"})
        )
        await _worker_para(session).ejecutar_un_trabajo(session)

    trabajo = await session.scalar(select(SyncJob).where(SyncJob.user_id == usuario.id))
    assert trabajo.status == EstadoJob.FAILED.value


async def test_sin_token_credencial_el_trabajo_falla(session: AsyncSession, usuario: User) -> None:
    await sync_queue.encolar(session, usuario.id)

    await _worker_para(session).ejecutar_un_trabajo(session)

    trabajo = await session.scalar(select(SyncJob).where(SyncJob.user_id == usuario.id))
    assert trabajo.status == EstadoJob.FAILED.value


async def test_sin_cuentas_de_juego_no_hay_error(
    session: AsyncSession, usuario: User, clave: str
) -> None:
    """Un trabajo sin cuentas se da por hecho, no por fallido: es configuracion, no error."""
    await _preparar(session, usuario, clave, con_cuentas=False)
    await sync_queue.encolar(session, usuario.id)

    await _worker_para(session).ejecutar_un_trabajo(session)

    trabajo = await session.scalar(select(SyncJob).where(SyncJob.user_id == usuario.id))
    assert trabajo.status == EstadoJob.DONE.value


def _worker_para(session: AsyncSession) -> Worker:
    """Worker sobre la sesion del test y con un cliente sin esperas ni reintentos."""
    return Worker(_factory_para(session), client_factory=_cliente_rapido)


def _factory_para(session: AsyncSession | None) -> async_sessionmaker[AsyncSession]:
    if session is None:
        from app.db.session import SessionLocal

        return SessionLocal
    return async_sessionmaker(lambda: session, expire_on_commit=False)


def _cliente_rapido(token: str) -> ClienteBallchasing:
    """Cliente con el limite y el backoff desactivados: los tests no deben esperar."""
    return ClienteBallchasing(
        token,
        limitador=LimitadorDePeticiones(por_segundo=1000, por_hora=1000, por_dia=1000),
        max_intentos=1,
        espera_base=0.001,
    )
