"""Caracterizacion de los eventos que emite PipelineRAG.ejecutar (F-19).

Fija el orden de las fases, el consulta_id compartido y el camino de error
ANTES de refactorizar `ejecutar` (complejidad ciclomatica 44), para que el
refactor no cambie lo que ve la Sala de Control en vivo.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.observability import (
    FaseCompletada,
    FaseIniciada,
    PipelineCompletado,
    PipelineError,
)
from src.application.services.hybrid_searcher import HybridSearcher
from src.application.services.pipeline_rag import PipelineRAG
from src.application.services.reranker_service import RerankerService
from src.domain.entities.fragmento import Fragmento


class _Bus:
    def __init__(self) -> None:
        self.eventos: list[object] = []

    async def publish(self, evento: object) -> None:
        self.eventos.append(evento)


def _frag(qid: str) -> Fragmento:
    return Fragmento(
        id=None,
        norma_id=1,
        obra_id=None,
        expediente_id=None,
        qdrant_point_id=qid,
        texto="...",
        padre_ref_id=None,
        padre_ref_key=None,
        nivel_jerarquico=4,
        metadatos=None,
        tipo_chunk="articulo_simple",
    )


def _pipeline(bus: _Bus, *, expansor=None, buscador_falla: bool = False) -> PipelineRAG:
    frag = _frag("a")
    buscador = MagicMock(spec=HybridSearcher)
    if buscador_falla:
        buscador.buscar = AsyncMock(side_effect=RuntimeError("qdrant caido"))
    else:
        buscador.buscar = AsyncMock(return_value=[(frag, 0.8)])
    reranker = MagicMock(spec=RerankerService)
    reranker.aplicar = AsyncMock(return_value=[(frag, 0.9)])
    config = MagicMock()
    config.get_config = AsyncMock(
        return_value=MagicMock(top_k_denso=40, top_k_lexico=20, top_k_final=7)
    )
    return PipelineRAG(
        buscador=buscador,
        reranker_svc=reranker,
        config_repo=config,
        expansor=expansor,
        event_bus=bus,  # type: ignore[arg-type]
    )


async def _drenar() -> None:
    """Deja correr las tareas de publicacion en segundo plano."""
    for _ in range(5):
        await asyncio.sleep(0)


def _secuencia(bus: _Bus) -> list[tuple[str, str]]:
    return [(type(e).__name__, getattr(e, "fase", "")) for e in bus.eventos]


@pytest.mark.asyncio
async def test_secuencia_de_eventos_sin_expansor() -> None:
    bus = _Bus()

    await _pipeline(bus).ejecutar(
        consulta="plazo de apelacion", usuario_id=1, expediente_id=None, consulta_id=77
    )
    await _drenar()

    assert _secuencia(bus) == [
        ("FaseIniciada", "entendiendo"),
        ("FaseCompletada", "entendiendo"),
        ("FaseIniciada", "buscando"),
        ("FaseCompletada", "buscando"),
        ("FaseIniciada", "reordenando"),
        ("FaseCompletada", "reordenando"),
        ("PipelineCompletado", "generando"),
    ]
    assert {e.consulta_id for e in bus.eventos} == {77}  # type: ignore[attr-defined]
    assert isinstance(bus.eventos[0], FaseIniciada)
    assert isinstance(bus.eventos[1], FaseCompletada)
    assert isinstance(bus.eventos[-1], PipelineCompletado)
    assert bus.eventos[-1].fragmentos_count == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_secuencia_de_eventos_con_expansor() -> None:
    bus = _Bus()
    expandido = MagicMock(trazabilidad=None)
    expansor = MagicMock()
    expansor.expandir = AsyncMock(return_value=expandido)

    salida = await _pipeline(bus, expansor=expansor).ejecutar(
        consulta="plazo de apelacion", usuario_id=1, expediente_id=None, consulta_id=5
    )
    await _drenar()

    assert salida is expandido
    assert _secuencia(bus)[-3:] == [
        ("FaseIniciada", "expandiendo"),
        ("FaseCompletada", "expandiendo"),
        ("PipelineCompletado", "generando"),
    ]


@pytest.mark.asyncio
async def test_fallo_de_una_fase_publica_pipeline_error_y_relanza() -> None:
    bus = _Bus()

    with pytest.raises(RuntimeError, match="qdrant caido"):
        await _pipeline(bus, buscador_falla=True).ejecutar(
            consulta="plazo de apelacion", usuario_id=1, expediente_id=None, consulta_id=9
        )
    await _drenar()

    error = bus.eventos[-1]
    assert isinstance(error, PipelineError)
    assert error.fase_fallida == "buscando"
    assert "qdrant caido" in error.mensaje_error
    assert error.consulta_id == 9


@pytest.mark.asyncio
async def test_sin_consulta_id_se_genera_uno_compartido_por_todos_los_eventos() -> None:
    bus = _Bus()

    await _pipeline(bus).ejecutar(consulta="plazo", usuario_id=1, expediente_id=None)
    await _drenar()

    ids = {e.consulta_id for e in bus.eventos}  # type: ignore[attr-defined]
    assert len(ids) == 1
    assert 0 <= ids.pop() < 2**31
