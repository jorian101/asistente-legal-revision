"""Bus de eventos in-memory para observabilidad del pipeline RAG (Sprint 7).

Protocol + implementación in-memory con asyncio.Queue por subscriptor.
No persiste: solo entrega en vivo a subscriptores conectados via SSE.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Protocol

from src.application.observability.pipeline_events import EventoPipelineUnion

logger = logging.getLogger(__name__)


class EventBus(Protocol):
    """Bus de eventos: publica a todos los subscriptores."""

    async def publish(self, evento: EventoPipelineUnion) -> None:
        """Publica un evento a todos los subscriptores activos."""
        ...

    async def subscribe(self) -> AsyncIterator[EventoPipelineUnion]:
        """Retorna un iterador async que yielda eventos publicados.

        Limpieza automática: al cerrar el iterador (o al desconectar SSE),
        el subscriptor se elimina del bus.
        """
        ...


class InMemoryEventBus:
    """Implementación in-memory con asyncio.Queue por subscriptor.

    Cada subscriptor recibe su propia queue. Al desconectar, se limpia.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[EventoPipelineUnion]] = set()

    def cantidad_suscriptores(self) -> int:
        """Cantidad de subscriptores SSE conectados (HU-22: sesiones activas)."""
        return len(self._subscribers)

    async def publish(self, evento: EventoPipelineUnion) -> None:
        """Publica a todos los subscriptores (non-blocking, drop si queue llena)."""
        if not self._subscribers:
            return
        for q in self._subscribers:
            try:
                q.put_nowait(evento)
            except asyncio.QueueFull:
                logger.warning("Queue llena, evento descartado para un subscriptor")

    async def subscribe(self) -> AsyncIterator[EventoPipelineUnion]:
        """Crea una queue para este subscriptor y yielda eventos.

        La queue se limpia automáticamente cuando el iterador se cierra
        (cuando el cliente SSE se desconecta).
        """
        q: asyncio.Queue[EventoPipelineUnion] = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        logger.debug("Nuevo subscriptor al bus (total: %d)", len(self._subscribers))
        try:
            while True:
                evento = await q.get()
                yield evento
        finally:
            self._subscribers.discard(q)
            logger.debug("Subscriptor desconectado (total: %d)", len(self._subscribers))


# Singleton in-memory para la app
_event_bus: InMemoryEventBus | None = None


def get_event_bus() -> InMemoryEventBus:
    """Obtiene o crea el singleton del bus."""
    global _event_bus
    if _event_bus is None:
        _event_bus = InMemoryEventBus()
    return _event_bus
