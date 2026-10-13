"""Cola de trabajos de sincronizacion sobre la tabla `sync_jobs`.

Ver `docs/adr/0002-cola-en-postgres.md`: no hay Redis, la cola son filas.
"""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.replay import UserReplay
from app.db.models.sync import EstadoJob, SyncJob, SyncState

logger = structlog.get_logger(__name__)

# Un trabajo que dura mas de esto se da por muerto y se vuelve a encolar.
TRABAJO_ABANDONADO_MINUTOS = 30


async def hay_pendientes(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """Si el usuario ya tiene un trabajo en cola o en curso."""
    pendiente = await session.scalar(
        select(SyncJob.id)
        .where(
            SyncJob.user_id == user_id,
            SyncJob.status.in_([EstadoJob.QUEUED.value, EstadoJob.RUNNING.value]),
        )
        .limit(1)
    )
    return pendiente is not None


async def encolar(session: AsyncSession, user_id: uuid.UUID, tipo: str = "full") -> SyncJob:
    """Encola una sincronizacion.

    Si ya hay un trabajo pendiente del mismo tipo se devuelve ese en vez de encolar
    otro: pulsar el boton diez veces no debe generar diez sincronizaciones.
    """
    pendiente = await session.scalar(
        select(SyncJob)
        .where(
            SyncJob.user_id == user_id,
            SyncJob.type == tipo,
            SyncJob.status.in_([EstadoJob.QUEUED.value, EstadoJob.RUNNING.value]),
        )
        .order_by(SyncJob.created_at)
        .limit(1)
    )
    if pendiente is not None:
        logger.info("sync.ya_encolado", user_id=str(user_id), job=str(pendiente.id))
        return pendiente

    trabajo = SyncJob(
        user_id=user_id,
        type=tipo,
        status=EstadoJob.QUEUED.value,
        run_after=datetime.now(UTC),
    )
    session.add(trabajo)
    await session.commit()
    await session.refresh(trabajo)
    logger.info("sync.encolado", user_id=str(user_id), job=str(trabajo.id))
    return trabajo


async def reclamar(session: AsyncSession) -> SyncJob | None:
    """Toma el siguiente trabajo pendiente, sin bloquear a los demas consumidores.

    `FOR UPDATE SKIP LOCKED` es lo que permite que dos workers simultaneos no cojan el
    mismo trabajo. En SQLite no existe, pero los tests corren de uno en uno.
    """
    trabajo = await session.scalar(
        select(SyncJob)
        .where(
            SyncJob.status == EstadoJob.QUEUED.value,
            SyncJob.run_after <= datetime.now(UTC),
        )
        .order_by(SyncJob.run_after)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if trabajo is None:
        return None

    trabajo.status = EstadoJob.RUNNING.value
    trabajo.attempts += 1
    trabajo.started_at = datetime.now(UTC)
    trabajo.last_error = None
    await session.commit()
    await session.refresh(trabajo)
    logger.info("sync.reclamado", job=str(trabajo.id), user_id=str(trabajo.user_id))
    return trabajo


async def devolver_abandonados(session: AsyncSession) -> int:
    """Recupera trabajos que se quedaron en `running`.

    Pasa cuando el proceso se muere a mitad (Render lo reinicia, el despliegue duerme
    el servicio). Como la ingesta es idempotente, volver a encolarlos no rompe nada.
    """
    limite = datetime.now(UTC) - timedelta(minutes=TRABAJO_ABANDONADO_MINUTOS)
    resultado = await session.execute(
        update(SyncJob)
        .where(
            SyncJob.status == EstadoJob.RUNNING.value,
            SyncJob.started_at < limite,
        )
        .values(status=EstadoJob.QUEUED.value, run_after=datetime.now(UTC))
    )
    await session.commit()
    devueltos = resultado.rowcount or 0  # type: ignore[attr-defined]
    if devueltos:
        logger.warning("sync.trabajos_devueltos", cantidad=devueltos)
    return devueltos


async def completar(
    session: AsyncSession,
    trabajo: SyncJob,
    nuevos: int,
    omitidos: int,
    ultima_partida: datetime | None = None,
) -> None:
    """Marca el trabajo como terminado y actualiza el estado del usuario."""
    trabajo.status = EstadoJob.DONE.value
    trabajo.finished_at = datetime.now(UTC)
    trabajo.replays_nuevos = nuevos
    trabajo.replays_omitidos = omitidos
    await session.commit()

    await actualizar_estado(
        session,
        trabajo.user_id,
        ultima_partida=ultima_partida,
        sumar_replays=nuevos,
    )
    logger.info(
        "sync.trabajo_completado",
        job=str(trabajo.id),
        user_id=str(trabajo.user_id),
        nuevos=nuevos,
        omitidos=omitidos,
    )


async def reprogramar(session: AsyncSession, trabajo: SyncJob, motivo: str) -> None:
    """Deja el trabajo para mas tarde sin consumir un fallo definitivo.

    Es lo que se hace ante un 429: el problema es la cuota, no el usuario, asi que no
    debe aparecer como fallo.
    """
    trabajo.status = EstadoJob.QUEUED.value
    trabajo.last_error = motivo[:500]
    trabajo.run_after = datetime.now(UTC) + trabajo.espera_reintento()
    await session.commit()
    logger.warning(
        "sync.reprogramado",
        job=str(trabajo.id),
        user_id=str(trabajo.user_id),
        intentos=trabajo.attempts,
        proximo=trabajo.run_after.isoformat(),
        motivo=motivo[:200],
    )


async def fallar(session: AsyncSession, trabajo: SyncJob, error: Exception) -> None:
    """Marca el trabajo como fallido definitivamente."""
    trabajo.status = EstadoJob.FAILED.value
    trabajo.finished_at = datetime.now(UTC)
    trabajo.last_error = f"{type(error).__name__}: {error}"[:500]
    await session.commit()
    logger.error(
        "sync.trabajo_fallido",
        job=str(trabajo.id),
        user_id=str(trabajo.user_id),
        intentos=trabajo.attempts,
        error=str(error)[:200],
    )


async def obtener_estado(session: AsyncSession, user_id: uuid.UUID) -> SyncState | None:
    return await session.get(SyncState, user_id)


async def obtener_o_crear_estado(session: AsyncSession, user_id: uuid.UUID) -> SyncState:
    estado = await session.get(SyncState, user_id)
    if estado is None:
        estado = SyncState(user_id=user_id)
        session.add(estado)
        await session.commit()
        await session.refresh(estado)
    return estado


async def actualizar_estado(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    ultima_partida: datetime | None = None,
    sumar_replays: int = 0,
    auto_sync: bool | None = None,
) -> SyncState:
    """Actualiza el progreso del usuario."""
    estado = await obtener_o_crear_estado(session, user_id)
    estado.last_synced_at = datetime.now(UTC)
    if ultima_partida is not None and (
        estado.last_replay_date is None or ultima_partida > estado.last_replay_date
    ):
        estado.last_replay_date = ultima_partida
    if sumar_replays:
        total = await session.scalar(
            select(func.count()).select_from(UserReplay).where(UserReplay.user_id == user_id)
        )
        estado.total_replays = int(total or 0)
    if auto_sync is not None:
        estado.auto_sync = auto_sync
    await session.commit()
    await session.refresh(estado)
    return estado


async def ultimo_trabajo(session: AsyncSession, user_id: uuid.UUID) -> SyncJob | None:
    return await session.scalar(
        select(SyncJob).where(SyncJob.user_id == user_id).order_by(SyncJob.created_at.desc())
    )


async def exigir_credencial(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Comprueba que el usuario puede sincronizar antes de encolar nada."""
    from app.services import credentials as servicio_credentials

    if await servicio_credentials.obtener_credencial(session, user_id) is None:
        raise AppError(
            status_code=409,
            code="missing_ballchasing_token",
            message="Primero tienes que guardar un token de Ballchasing.",
        )
