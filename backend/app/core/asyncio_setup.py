"""Ajustes del bucle de eventos de asyncio.

En Windows, asyncio usa por defecto el bucle `Proactor`, que psycopg no soporta en modo
asincrono. Hay que forzar `Selector`, que es lo que ya se usa en Linux y en Render, para
que el mismo codigo funcione en desarrollo y en produccion.
"""

import asyncio
import sys


def ensure_compatible_event_loop() -> None:
    """Fuerza `WindowsSelectorEventLoopPolicy` en Windows. Idempotente."""
    if sys.platform != "win32":
        return

    current = type(asyncio.get_event_loop_policy()).__name__
    if current == "WindowsSelectorEventLoopPolicy":
        return

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
