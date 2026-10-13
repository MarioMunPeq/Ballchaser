"""Cola de sincronizacion y estado por usuario.

La cola son filas de esta tabla, no Redis (ver `docs/adr/0002-cola-en-postgres.md`).
Se toma un trabajo con `SELECT ... FOR UPDATE SKIP LOCKED`, que es lo que permite que
varios consumidores repartan trabajo sin bloquearse.
"""

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UtcDateTime

# Cuanto espera un trabajo antes de volver a intentarlo tras un 429, por intento.
REINTENTO_BASE_SEGUNDOS = 60


class EstadoJob(StrEnum):
    """Ciclo de vida de un trabajo de sincronizacion."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class SyncJob(Base):
    """Un trabajo de sincronizacion para un usuario."""

    __tablename__ = "sync_jobs"
    __table_args__ = (
        # Consulta principal del worker: trabajos pendientes por fecha.
        Index("ix_sync_jobs_status_run_after", "status", "run_after"),
        Index("ix_sync_jobs_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Por ahora solo 'full'; queda el hueco para sincronizaciones parciales.
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="full")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=EstadoJob.QUEUED.value, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Cuándo puede volver a intentarse: un 429 se reprograma mas adelante.
    run_after: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, server_default=func.current_timestamp()
    )
    last_error: Mapped[str | None] = mapped_column(String(500))
    # Contadores de la ultima ejecucion, para el endpoint de estado.
    replays_nuevos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    replays_omitidos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        default=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    def __repr__(self) -> str:
        return f"<SyncJob {self.user_id} {self.status} intentos={self.attempts}>"

    @property
    def pendiente(self) -> bool:
        return self.status in (EstadoJob.QUEUED.value, EstadoJob.RUNNING.value)

    @property
    def texto_de_error(self) -> str | None:
        """El error recortado: `last_error` es una columna corta."""
        if not self.last_error:
            return None
        return self.last_error[:500]

    def espera_reintento(self) -> timedelta:
        """Espera antes del siguiente intento, con tope.

        Crece con los intentos para no castigar a Ballchasing cuando el problema es
        suyo (su cuota o una caida), y se queda en un minuto como minimo util.
        """
        minutos = min(2 ** (self.attempts - 1), 60) if self.attempts > 0 else 1
        return timedelta(seconds=max(REINTENTO_BASE_SEGUNDOS // 60, 1) * 60 * minutos)


class SyncState(Base):
    """Progreso de la sincronizacion de un usuario."""

    __tablename__ = "sync_state"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    # Fecha de la ultima partida ingerida: permite pedir solo lo posterior.
    last_replay_date: Mapped[datetime | None] = mapped_column(UtcDateTime)
    total_replays: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    auto_sync: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return f"<SyncState {self.user_id} total={self.total_replays}>"
