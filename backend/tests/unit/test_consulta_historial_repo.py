"""Tests del repositorio ConsultaHistorialRepoImpl (PostgreSQL).

Cubre los dos bugs corregidos en la revision pre-PR de Sprint 3:
1. `guardar` debe commitear (SQLAlchemy 2.0 AsyncSession no autocommitea).
2. `listar_por_usuario` valida usuario_id > 0 (Regla 4 defensa en repo).

La sesion SQLAlchemy se mockea para no requerir DB live.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.postgres.repos.consulta_historial_repo import (
    ConsultaHistorialRepoImpl,
)
from src.domain.entities.consulta_historial import ConsultaHistorial


def _make_historial() -> ConsultaHistorial:
    return ConsultaHistorial(
        id=None,
        expediente_id=None,
        usuario_id=1,
        pregunta="test pregunta",
        respuesta=None,
        tipo_respuesta="consulta_simple",
        fuentes_recuperadas={"tipo_respuesta": "consulta_simple"},
        latencia_ms=10,
        modelo_llm=None,
    )


def _mock_model() -> MagicMock:
    """Simula el ORM model devuelto por refresh()."""
    m = MagicMock()
    m.id = 99
    m.created_at = datetime(2026, 8, 5, 14, 0, 0)
    return m


@pytest.mark.asyncio
async def test_guardar_hace_commit_explicito() -> None:
    """Regresión commit: guardar debe llamar session.commit() o el INSERT
    se pierde en el rollback del request (AsyncSession no autocommitea).

    Bug encontrado por revision pre-PR de Sprint 3;系统地 presente en
    otros repos HTTP del proyecto (ver test_ingestion/test_explicit_commit.py).
    """
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    # refresh devuelve el id asignado al model que recibe.
    session.refresh = AsyncMock(side_effect=lambda m: setattr(m, "id", 99))
    session.commit = AsyncMock()

    repo = ConsultaHistorialRepoImpl(session)
    historial = _make_historial()

    resultado = await repo.guardar(historial)

    assert session.flush.await_count == 1
    assert session.refresh.await_count == 1
    # CRITICAL fix: commit explicito, sin esto el INSERT se pierde.
    assert session.commit.await_count == 1
    assert resultado.id == 99


def _make_model_with_id(id_: int) -> MagicMock:
    m = MagicMock()
    m.id = id_
    m.created_at = datetime(2026, 8, 5, 14, 0, 0)
    return m


@pytest.mark.asyncio
async def test_listar_por_usuario_rechaza_usuario_id_invalido() -> None:
    """Regla 4 defensa en repo: usuario_id > 0 (no bool, no 0, no None)."""
    session = MagicMock()
    session.execute = AsyncMock()
    repo = ConsultaHistorialRepoImpl(session)

    for invalido in [0, -1, None, True, False]:
        with pytest.raises(ValueError):
            await repo.listar_por_usuario(
                usuario_id=invalido,  # type: ignore[arg-type]
                expediente_id=None,
                pagina=1,
                por_pagina=10,
            )

    # Si execute nunca se llama, el test pasó el guard.
    assert session.execute.await_count == 0


@pytest.mark.asyncio
async def test_actualizar_metadatos_actualiza_y_commitea() -> None:
    """Task A: actualizar_metadatos setea tipo/fuentes/latencia y commitea."""
    session = MagicMock()
    model = MagicMock()
    model.id = 42
    model.tipo_respuesta = None
    model.fuentes_recuperadas = None
    model.latencia_ms = None
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(one_or_none=MagicMock(return_value=model)))
        )
    )
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    repo = ConsultaHistorialRepoImpl(session)
    resultado = await repo.actualizar_metadatos(
        42,
        tipo_respuesta="auto_vista_consulta",
        fuentes_recuperadas={"fragmentos_count": 1},
        latencia_ms=75,
    )

    assert model.tipo_respuesta == "auto_vista_consulta"
    assert model.fuentes_recuperadas == {"fragmentos_count": 1}
    assert model.latencia_ms == 75
    assert session.flush.await_count == 1
    assert session.commit.await_count == 1
    assert resultado is not None
    assert resultado.id == 42


@pytest.mark.asyncio
async def test_actualizar_respuesta_parcial_no_toca_estado() -> None:
    """P1: a diferencia de actualizar_respuesta, el parcial NO marca 'completado'.

    Si tocara estado, streamResume (que polea por estado) daria la consulta
    por terminada al primer parcial en vez de seguir hasta el cierre real.
    """
    session = MagicMock()
    model = MagicMock()
    model.id = 42
    model.respuesta = None
    model.estado = "en_progreso"
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(one_or_none=MagicMock(return_value=model)))
        )
    )
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    repo = ConsultaHistorialRepoImpl(session)
    await repo.actualizar_respuesta_parcial(42, "texto parcial acumulado")

    assert model.respuesta == "texto parcial acumulado"
    assert model.estado == "en_progreso"  # sin tocar
    assert session.flush.await_count == 1
    assert session.commit.await_count == 1


@pytest.mark.asyncio
async def test_actualizar_respuesta_parcial_inexistente_no_rompe() -> None:
    """Silencioso si el historial_id no existe — el parcial es best-effort."""
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(one_or_none=MagicMock(return_value=None)))
        )
    )
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    repo = ConsultaHistorialRepoImpl(session)

    await repo.actualizar_respuesta_parcial(999, "x")

    assert session.flush.await_count == 0
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_actualizar_metadatos_inexistente_devuelve_none() -> None:
    """Si el historial no existe, actualizar_metadatos devuelve None (sin raise)."""
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(one_or_none=MagicMock(return_value=None)))
        )
    )
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    repo = ConsultaHistorialRepoImpl(session)

    resultado = await repo.actualizar_metadatos(
        999,
        tipo_respuesta="consulta_simple",
        fuentes_recuperadas=None,
        latencia_ms=None,
    )
    assert resultado is None
    # No se hace flush/commit si no existe.
    assert session.flush.await_count == 0
    assert session.commit.await_count == 0
