"""Publicacion de eventos en segundo plano sin perder la tarea ni sus errores (F-20).

`asyncio.create_task` sin guardar la referencia permite que el recolector
descarte la tarea antes de terminar, y una excepcion en `publish` se pierde.
Mismo patron que `_PENDING_FINALIZE` de generar_borrador.py.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Protocol

from src.application.observability.pipeline_events import EventoPipelineUnion

log = logging.getLogger(__name__)

_TAREAS: set[asyncio.Task[None]] = set()


class Publicador(Protocol):
    """Lo unico que necesita el helper del bus (InMemoryEventBus y EventBus lo cumplen)."""

    async def publish(self, evento: EventoPipelineUnion) -> None: ...


def publicar_en_segundo_plano(bus: Publicador, evento: EventoPipelineUnion) -> asyncio.Task[None]:
    """Lanza `bus.publish(evento)` guardando la tarea hasta que termine."""
    tarea = asyncio.create_task(bus.publish(evento))
    _TAREAS.add(tarea)
    tarea.add_done_callback(_terminada)
    return tarea


def _terminada(tarea: asyncio.Task[None]) -> None:
    _TAREAS.discard(tarea)
    if not tarea.cancelled() and (error := tarea.exception()) is not None:
        log.error("Fallo al publicar el evento en segundo plano", exc_info=error)


def nuevo_consulta_id() -> int:
    """Id de consulta de 31 bits para eventos cuando el caller no aporta uno.

    Aleatorio: el `hash((...))` anterior colisionaba si dos consultas iguales
    llegaban en el mismo milisegundo.
    """
    return secrets.randbits(31)
