"""Tests unitarios del use case ObtenerMetricasSalud (HU-22).

Cubre:
- Happy path: pings ok + conteo de suscriptores del bus.
- Componente caido: se reporta con ok=False sin lanzar excepcion.
"""

from __future__ import annotations

import asyncio

import pytest

from src.application.admin.obtener_metricas_salud import ejecutar
from src.application.observability.event_bus import InMemoryEventBus
from src.application.ports.salud_sistema import SaludInfraestructura


class _FakeSaludRepo:
    def __init__(self, estado: SaludInfraestructura) -> None:
        self._estado = estado
        self.llamadas = 0

    async def verificar(self) -> SaludInfraestructura:
        self.llamadas += 1
        return self._estado


@pytest.mark.asyncio
async def test_salud_ok_reporta_componentes_y_sesiones() -> None:
    repo = _FakeSaludRepo(
        SaludInfraestructura(postgres_ok=True, qdrant_ok=True, qdrant_puntos=3109)
    )

    resultado = await ejecutar(salud_repo=repo, bus=InMemoryEventBus())

    assert resultado.postgres_ok is True
    assert resultado.qdrant_ok is True
    assert resultado.qdrant_puntos == 3109
    assert resultado.sesiones_activas == 0
    assert repo.llamadas == 1


@pytest.mark.asyncio
async def test_salud_cuenta_suscriptores_sse_vivos() -> None:
    repo = _FakeSaludRepo(SaludInfraestructura(postgres_ok=True, qdrant_ok=True, qdrant_puntos=10))
    bus = InMemoryEventBus()
    # White-box: simular 2 subscriptores SSE conectados (cada uno tiene queue).
    bus._subscribers.add(asyncio.Queue(maxsize=1))
    bus._subscribers.add(asyncio.Queue(maxsize=1))

    resultado = await ejecutar(salud_repo=repo, bus=bus)

    assert resultado.sesiones_activas == 2


@pytest.mark.asyncio
async def test_salud_qdrant_caido_no_lanza() -> None:
    repo = _FakeSaludRepo(SaludInfraestructura(postgres_ok=True, qdrant_ok=False, qdrant_puntos=0))

    resultado = await ejecutar(salud_repo=repo, bus=InMemoryEventBus())

    assert resultado.qdrant_ok is False
    assert resultado.qdrant_puntos == 0
    assert resultado.postgres_ok is True


@pytest.mark.asyncio
async def test_salud_todo_caido_retorna_estado_degradado() -> None:
    repo = _FakeSaludRepo(SaludInfraestructura(postgres_ok=False, qdrant_ok=False, qdrant_puntos=0))

    resultado = await ejecutar(salud_repo=repo, bus=InMemoryEventBus())

    assert resultado.postgres_ok is False
    assert resultado.qdrant_ok is False
