"""Endpoints de sincronizacion.

`POST /sync` no sincroniza: encola un trabajo. El worker lo coge cuando puede, que es
lo que permite que un trabajo largo no bloquee una peticion HTTP.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import CurrentIdentity
from app.db.session import get_session
from app.schemas.sync import SyncAjustesEntrada, SyncEncoladoRespuesta, SyncEstadoRespuesta
from app.services import game_accounts, sync_queue, users

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/sync",
    response_model=SyncEncoladoRespuesta,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Encolar una sincronizacion",
)
async def encolar_sync(identity: CurrentIdentity, session: SessionDep) -> SyncEncoladoRespuesta:
    """Pide sincronizar los replays del usuario.

    Si ya hay una sincronizacion pendiente, no se encola otra: el trabajo en curso ya
    recogera los replays nuevos.
    """
    user, _created = await users.get_or_create_user(session, identity)

    await sync_queue.exigir_credencial(session, user.id)

    cuentas = await game_accounts.listar(session, user.id)
    if not cuentas:
        raise AppError(
            status_code=409,
            code="missing_game_account",
            message="Anade antes una cuenta de juego para saber que replays son tuyos.",
        )

    pendientes = await sync_queue.hay_pendientes(session, user.id)
    trabajo = await sync_queue.encolar(session, user.id)

    return SyncEncoladoRespuesta(
        job_id=str(trabajo.id),
        status=trabajo.status,
        ya_estaba_encolada=pendientes,
    )


@router.get(
    "/sync/status", response_model=SyncEstadoRespuesta, summary="Estado de la sincronizacion"
)
async def estado_sync(identity: CurrentIdentity, session: SessionDep) -> SyncEstadoRespuesta:
    user, _created = await users.get_or_create_user(session, identity)

    trabajo = await sync_queue.ultimo_trabajo(session, user.id)
    estado = await sync_queue.obtener_estado(session, user.id)

    return SyncEstadoRespuesta(
        encolado=bool(trabajo and trabajo.pendiente),
        ultimo_job_id=str(trabajo.id) if trabajo else None,
        ultimo_estado=trabajo.status if trabajo else None,
        ultimo_error=trabajo.last_error if trabajo else None,
        replays_nuevos=trabajo.replays_nuevos if trabajo else 0,
        replays_omitidos=trabajo.replays_omitidos if trabajo else 0,
        last_synced_at=estado.last_synced_at if estado else None,
        last_replay_date=estado.last_replay_date if estado else None,
        total_replays=estado.total_replays if estado else 0,
        auto_sync=estado.auto_sync if estado else False,
        intentos=trabajo.attempts if trabajo else 0,
        proximo_intento=trabajo.run_after if trabajo and trabajo.pendiente else None,
    )


@router.patch("/me/sync-settings", summary="Activar o desactivar la sincronizacion automatica")
async def ajustar_sync(
    cuerpo: SyncAjustesEntrada, identity: CurrentIdentity, session: SessionDep
) -> SyncEstadoRespuesta:
    """El cron de GitHub Actions solo encola si esta activado."""
    user, _created = await users.get_or_create_user(session, identity)
    await sync_queue.actualizar_estado(session, user.id, auto_sync=cuerpo.auto_sync)
    return await estado_sync(identity, session)
