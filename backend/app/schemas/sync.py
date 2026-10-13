"""Esquemas de sincronizacion."""

from datetime import datetime

from pydantic import BaseModel, Field


class SyncEstadoRespuesta(BaseModel):
    """Como va la sincronizacion del usuario."""

    encolado: bool = Field(description="Si hay un trabajo pendiente o en curso.")
    ultimo_job_id: str | None = None
    ultimo_estado: str | None = Field(default=None, description="queued, running, done o failed.")
    ultimo_error: str | None = None
    replays_nuevos: int = 0
    replays_omitidos: int = 0
    last_synced_at: datetime | None = None
    last_replay_date: datetime | None = None
    total_replays: int = 0
    auto_sync: bool = False
    intentos: int = 0
    proximo_intento: datetime | None = None


class SyncEncoladoRespuesta(BaseModel):
    """Confirmacion de que la sincronizacion se ha encolado."""

    job_id: str
    status: str = Field(description="queued")
    ya_estaba_encolada: bool = Field(
        description="True si ya habia una sincronizacion pendiente y no se encola otra."
    )


class SyncAjustesEntrada(BaseModel):
    """Activar o desactivar la sincronizacion periodica."""

    auto_sync: bool
