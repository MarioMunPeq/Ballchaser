"""Limitador de peticiones para la API de Ballchasing.

Ballchasing no ofrece cabecera de cuota: si se excede, responde 429 y ya esta. Por eso
este modulo contabiliza lo que se pide y se autorregula *antes* de recibir el 429.

Tres limites: segundo, hora y dia. Cada uno es una bolsa que se rellena de forma continua;
si esta vacia, hay que esperar. Vive en memoria porque el servicio es una sola instancia;
si se reinicia, se reconstruye y se apoya en el manejo del 429.
"""

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class BolsaDeTokens:
    """Bolsa que se rellena a `por_segundo` y admite un pico de `capacidad`."""

    capacidad: float
    por_segundo: float
    tokens: float = field(init=False)
    _actualizado: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = self.capacidad
        self._actualizado = time.monotonic()

    def _rellenar(self) -> None:
        ahora = time.monotonic()
        self.tokens = min(
            self.capacidad, self.tokens + (ahora - self._actualizado) * self.por_segundo
        )
        self._actualizado = ahora

    def consumir(self) -> bool:
        self._rellenar()
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

    def segundos_hasta_tener(self) -> float:
        """Espera necesaria para poder consumir un token."""
        self._rellenar()
        if self.tokens >= 1:
            return 0.0
        return (1 - self.tokens) / self.por_segundo

    def hay_cupo(self) -> bool:
        self._rellenar()
        return self.tokens >= 1


class LimitadorDePeticiones:
    """Autoriza peticiones por segundo, por hora y por dia para un token."""

    def __init__(
        self,
        por_segundo: float = 2.0,
        por_hora: int = 500,
        por_dia: int = 10_000,
    ) -> None:
        self.bolsas = (
            BolsaDeTokens(capacidad=por_segundo, por_segundo=por_segundo),
            BolsaDeTokens(capacidad=por_hora, por_segundo=por_hora / 3600),
            BolsaDeTokens(capacidad=por_dia, por_segundo=por_dia / 86_400),
        )

    def esperar(self) -> float:
        """Bloquea hasta que haya cupo y consume uno. Devuelve los segundos esperados."""
        espera = max(bolsa.segundos_hasta_tener() for bolsa in self.bolsas)
        if espera > 0:
            time.sleep(espera)
        # Tras dormir se comprueba otra vez: el cupo pudo consumirse mientras tanto.
        for bolsa in self.bolsas:
            bolsa.consumir()
        return espera

    def hay_cupo(self) -> bool:
        """Hay cupo ahora mismo, sin esperar. Para el endpoint de estado."""
        return all(bolsa.hay_cupo() for bolsa in self.bolsas)


class RegistroDeLlamadas:
    """Ultimas llamadas realizadas, para diagnostico."""

    def __init__(self, capacidad: int = 100) -> None:
        self._eventos: deque[tuple[float, str, int]] = deque(maxlen=capacidad)

    def anotar(self, ruta: str, estado: int) -> None:
        self._eventos.append((time.time(), ruta, estado))

    @property
    def eventos(self) -> list[tuple[float, str, int]]:
        return list(self._eventos)
