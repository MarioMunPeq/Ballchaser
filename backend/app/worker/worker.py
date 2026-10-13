"""Worker que consume la cola de sincronizacion.

Vive en el mismo proceso que la API (una sola instancia, ver ADR 0002) y va sacando
trabajos en un bucle. Se puede arrancar y parar, asi que los tests pueden ejecutarlo
paso a paso sin esperas.
"""

import asyncio
from collections.abc import Callable

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import SessionLocal
from app.services import game_accounts, ingest
from app.services.ballchasing import ClienteBallchasing, CuotaAgotada, TokenInvalido
from app.services.credentials import leer_token
from app.services.sync_queue import (
    completar,
    devolver_abandonados,
    fallar,
    obtener_o_crear_estado,
    reclamar,
    reprogramar,
)

logger = structlog.get_logger(__name__)

# Cuanto duerme el bucle cuando no hay nada que hacer.
ESPERA_SIN_TRABAJOS = 5.0


class Worker:
    """Consumidor de `sync_jobs`.

    `client_factory` existe para los tests: permite sustituir el cliente real por uno
    sin esperas ni reintentos, sin tocar la logica del worker.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        client_factory: Callable[[str], ClienteBallchasing] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._client_factory = client_factory or ClienteBallchasing
        self._tarea: asyncio.Task[None] | None = None
        self._parar = asyncio.Event()

    # --- ejecucion de un trabajo ---

    async def ejecutar_un_trabajo(self, session: AsyncSession) -> bool:
        """Toma un trabajo y lo lleva a cabo. Devuelve `False` si no habia ninguno.

        Aqui es donde se decide que es un fallo recuperable (429, caida de
        Ballchasing) y que no (token invalido).
        """
        trabajo = await reclamar(session)
        if trabajo is None:
            return False

        user_id = trabajo.user_id
        try:
            token = await leer_token(session, user_id)
            if token is None:
                await fallar(session, trabajo, TokenInvalido("No hay token guardado."))
                return True

            cuentas = await game_accounts.listar(session, user_id)
            if not cuentas:
                await obtener_o_crear_estado(session, user_id)
                await completar(session, trabajo, nuevos=0, omitidos=0)
                logger.info("sync.sin_cuentas_de_juego", user_id=str(user_id))
                return True

            cliente = self._client_factory(token)
            try:
                resumen = await ingest.sincronizar(session, cliente, cuentas, user_id)
            finally:
                await cliente.cerrar()

            await completar(
                session,
                trabajo,
                nuevos=resumen.nuevos,
                omitidos=resumen.omitidos,
                ultima_partida=resumen.ultima_partida,
            )
            logger.info(
                "sync.hecho",
                user_id=str(user_id),
                nuevos=resumen.nuevos,
                fallidos=resumen.fallidos,
            )

        except CuotaAgotada as exc:
            # Cuota agotada: no es culpa del usuario ni un fallo definitivo. El
            # trabajo vuelve a la cola con espera creciente.
            await reprogramar(session, trabajo, str(exc))
        except TokenInvalido as exc:
            await fallar(session, trabajo, exc)
        except Exception as exc:
            await fallar(session, trabajo, exc)

        return True

    # --- bucle ---

    async def _bucle(self) -> None:
        logger.info("worker.arrancado")
        # Al arrancar, se recuperan los trabajos que quedaron a medias.
        async with self._session_factory() as session:
            await devolver_abandonados(session)

        while not self._parar.is_set():
            try:
                async with self._session_factory() as session:
                    hubo_trabajo = await self.ejecutar_un_trabajo(session)
            except Exception:
                # El bucle no puede morir por un fallo puntual: se registra y sigue.
                logger.error("worker.error_en_bucle", exc_info=True)
                hubo_trabajo = False

            if not hubo_trabajo:
                try:
                    await asyncio.wait_for(self._parar.wait(), timeout=ESPERA_SIN_TRABAJOS)
                except TimeoutError:
                    continue

        logger.info("worker.parado")

    def arrancar(self) -> None:
        """Arranca el bucle en segundo plano (idempotente)."""
        if self._tarea is not None and not self._tarea.done():
            return
        self._parar = asyncio.Event()
        self._tarea = asyncio.create_task(self._bucle(), name="sync-worker")

    async def parar(self) -> None:
        """Pide al bucle que termine y espera a que lo haga."""
        self._parar.set()
        if self._tarea is not None:
            try:
                await asyncio.wait_for(self._tarea, timeout=10)
            except TimeoutError:
                logger.warning("worker.no_termino")
            self._tarea = None


def construir_worker() -> Worker:
    """Worker con la sesion real de la aplicacion."""
    return Worker(SessionLocal)
