"""Cliente de la API de Ballchasing.

Decisiones que vienen de comprobar el servicio real (ver `docs/ballchasing-api.md`):

- La cabecera es `Authorization: <token>`, sin `Bearer`.
- El listado devuelve `list` / `count` / `next`, no `replays`.
- El enlace `next` se sigue **literalmente**: si se le anaden parametros, el cursor se
  ignora y se vuelve a la primera pagina, sin avisar.
- No hay endpoint de perfil, asi que validar un token cuesta una llamada al listado.
- El 429 llega con un cuerpo de broma de Rocket League en el campo `error`, asi que se
  decide por el codigo HTTP y no por el texto.
"""

import asyncio
import random
from types import TracebackType
from typing import Any, Self

import httpx
import structlog

from app.core.config import settings
from app.services.ballchasing.errors import (
    CuotaAgotada,
    ErrorBallchasing,
    RespuestaInvalida,
    TokenInvalido,
)
from app.services.ballchasing.rate_limit import LimitadorDePeticiones, RegistroDeLlamadas

logger = structlog.get_logger(__name__)

MAX_INTENTOS = 4
ESPERA_BASE = 0.5
MAX_ESPERA = 30.0


class ClienteBallchasing:
    """Cliente HTTP asincrono con limite de peticiones propio."""

    def __init__(
        self,
        token: str,
        *,
        cliente_http: httpx.AsyncClient | None = None,
        limitador: LimitadorDePeticiones | None = None,
        max_intentos: int = MAX_INTENTOS,
        espera_base: float = ESPERA_BASE,
    ) -> None:
        self._token = token
        self._max_intentos = max_intentos
        self._espera_base = espera_base
        self._limitador = limitador or LimitadorDePeticiones(
            por_segundo=settings.ballchasing_rate_per_second,
            por_hora=settings.ballchasing_rate_per_hour,
        )
        self.registro = RegistroDeLlamadas()
        self._propio = cliente_http is None
        self._cliente = cliente_http or httpx.AsyncClient(
            base_url=settings.ballchasing_base_url,
            timeout=20.0,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.cerrar()

    async def cerrar(self) -> None:
        if self._propio:
            await self._cliente.aclose()

    def _cabeceras(self) -> dict[str, str]:
        """La cabecera va en cada peticion, no en el cliente.

        Si se pusiera al construir el cliente, un cliente HTTP inyectado desde fuera
        (tests, otro servicio) se quedaria sin autorizacion y Ballchasing responderia
        401 por un fallo que no es del token.
        """
        return {"Authorization": self._token, "Accept": "application/json"}

    async def _get(self, ruta: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """GET con limite de peticiones y reintentos ante 429 y errores de red."""
        for intento in range(self._max_intentos):
            waited = await asyncio.to_thread(self._limitador.esperar)
            if waited > 0:
                logger.debug("ballchasing.limite_esperado", ruta=ruta, segundos=round(waited, 2))

            try:
                respuesta = await self._cliente.get(ruta, params=params, headers=self._cabeceras())
            except httpx.HTTPError as exc:
                if intento == self._max_intentos - 1:
                    raise ErrorBallchasing(f"Fallo de red hablando con Ballchasing: {exc}") from exc
                await asyncio.sleep(self._espera(intento))
                continue

            self.registro.anotar(ruta, respuesta.status_code)

            if respuesta.status_code == 401:
                # No se reintenta: el token no es valido.
                raise TokenInvalido("Ballchasing no reconoce el token.")

            if respuesta.status_code == 429:
                if intento == self._max_intentos - 1:
                    raise CuotaAgotada(
                        "Ballchasing mantiene el limite de peticiones tras varios intentos."
                    )
                espera = self._espera(intento)
                logger.warning(
                    "ballchasing.cuota", ruta=ruta, intento=intento + 1, espera=round(espera, 2)
                )
                await asyncio.sleep(espera)
                continue

            if respuesta.status_code >= 500:
                if intento == self._max_intentos - 1:
                    # Error de dominio, no HTTPStatusError: si escapara crudo, el
                    # endpoint responderia 500 en vez de 502 y el usuario culparia
                    # a su token cuando el problema es que Ballchasing esta caido.
                    raise ErrorBallchasing(
                        f"Ballchasing sigue con errores de servidor "
                        f"({respuesta.status_code}) tras {self._max_intentos} intentos."
                    )
                await asyncio.sleep(self._espera(intento))
                continue

            if respuesta.status_code >= 400:
                raise ErrorBallchasing(
                    f"Ballchasing devolvio {respuesta.status_code}: {self._detalle(respuesta)}"
                )

            return respuesta

        raise ErrorBallchasing("Se agotaron los intentos contra Ballchasing.")

    def _espera(self, intento: int) -> float:
        """Backoff exponencial con jitter, para no castigar siempre en el mismo instante."""
        base = min(self._espera_base * (2**intento), MAX_ESPERA)
        # Jitter: aqui no se quiere unpredictabilidad criptografica, sino que varios
        # workers no repitan el intento clavados en el milisegundo.
        return base * (0.5 + random.random() / 2)  # noqa: S311

    @staticmethod
    def _detalle(respuesta: httpx.Response) -> str:
        try:
            cuerpo = respuesta.json()
        except ValueError:
            return respuesta.text[:200]
        if isinstance(cuerpo, dict):
            # El campo `error` a veces trae texto de broma: se recorta y nada mas.
            return str(cuerpo.get("error", cuerpo))[:200]
        return str(cuerpo)[:200]

    async def validar_token(self) -> dict[str, Any]:
        """Comprueba el token contra Ballchasing. Es lo mas barato que existe.

        Lanza `TokenInvalido` si Ballchasing lo rechaza. Cuesta una llamada del cupo
        horario, asi que no se usa en bucles ni como comprobacion continua.
        """
        datos = await self.listar_replays(limit=1, solo_mios=True)
        return {"ok": True, "replays_visibles": len(datos.get("list", []))}

    async def listar_replays(
        self,
        *,
        limit: int = 100,
        solo_mios: bool = False,
        nombre_jugador: str | None = None,
        playlist: str | None = None,
        season: int | None = None,
        despues_de: str | None = None,
        antes_de: str | None = None,
        siguiente: str | None = None,
    ) -> dict[str, Any]:
        """Devuelve una pagina del listado con la forma real de la API."""
        if siguiente is not None:
            # El enlace `next` se sigue tal cual. Anadirle `count` hace que el
            # servidor ignore el cursor y devuelva la primera pagina otra vez.
            ruta = siguiente if siguiente.startswith("http") else f"/{siguiente}"
            respuesta = await self._get(ruta)
            return self._cuerpo(respuesta)

        if not 1 <= limit <= 200:
            raise ValueError("limit debe estar entre 1 y 200")

        params: dict[str, Any] = {"count": limit}
        if solo_mios:
            params["uploader"] = "me"
        if nombre_jugador:
            params["player-name"] = nombre_jugador
        if playlist:
            params["playlist"] = playlist
        if season is not None:
            params["season"] = season
        if despues_de:
            params["replay-date-after"] = despues_de
        if antes_de:
            params["replay-date-before"] = antes_de

        respuesta = await self._get("/replays", params=params)
        return self._cuerpo(respuesta)

    async def obtener_replay(self, replay_id: str) -> dict[str, Any]:
        """Detalle de un replay: objeto plano con `blue` y `orange`."""
        respuesta = await self._get(f"/replays/{replay_id}")
        return self._cuerpo(respuesta)

    @staticmethod
    def _cuerpo(respuesta: httpx.Response) -> dict[str, Any]:
        try:
            datos = respuesta.json()
        except ValueError as exc:
            raise RespuestaInvalida("Ballchasing no devolvio JSON.") from exc
        if not isinstance(datos, dict):
            raise RespuestaInvalida("Ballchasing devolvio un JSON inesperado.")
        return datos


def validar_formato_de_token(token: str) -> str:
    """Normaliza el token que escribe el usuario."""
    limpio = token.strip()
    if not limpio:
        raise ValueError("El token esta vacio")
    if limpio.lower().startswith("bearer "):
        # La API no usa `Bearer`, pero es un error facil de cometer al copiarlo de
        # otra parte; se limpia en vez de fallar con un 401 confuso.
        limpio = limpio[7:].strip()
    if len(limpio) > 512:
        raise ValueError("El token es demasiado largo")
    return limpio
