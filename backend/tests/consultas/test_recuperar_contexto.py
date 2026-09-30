"""Tests del use case RecuperarContexto.

Cubre:
- Ejecuta el pipeline y persiste en historial.
- respuesta es NULL en Sprint 3 (D11).
- Devuelve ResultadoConsulta con contexto y historial_id.
- La serializacion de fuentes_recuperadas es JSONB-compatible.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.consultas.recuperar_contexto import (
    ConsultaRequest,
    ResultadoConsulta,
    ejecutar,
)
from src.domain.entities.consulta_historial import ConsultaHistorial
from src.domain.entities.fragmento import Fragmento
from src.domain.value_objects.contexto_expandido import ContextoExpandido
from src.domain.value_objects.contexto_recuperado import ContextoRecuperado
from src.domain.value_objects.trazabilidad_pipeline import TrazabilidadPipeline


def _frag(qid: str) -> Fragmento:
    return Fragmento(
        id=1,
        norma_id=10,
        obra_id=None,
        expediente_id=None,
        qdrant_point_id=qid,
        texto="Articulo 1 CPPM.",
        padre_ref_id=None,
        padre_ref_key=None,
        nivel_jerarquico=4,
        metadatos=None,
        tipo_chunk="articulo_simple",
    )


def _make_dependencies() -> tuple:
    """Retorna (pipeline, historial_repo, saved_log)."""
    saved: list[ConsultaHistorial] = []

    contexto = ContextoRecuperado(
        fragmentos=(_frag("a"), _frag("b")),
        scores=(0.9, 0.7),
        query_original="plazo de apelacion?",
        tipo_respuesta="consulta_simple",
        expediente_id=None,
        latencia_ms=123,
    )

    pipeline = MagicMock()
    pipeline.ejecutar = AsyncMock(return_value=contexto)

    async def _guardar(historial: ConsultaHistorial) -> ConsultaHistorial:
        historial.id = 99
        historial.created_at = datetime(2026, 8, 4)
        saved.append(historial)
        return historial

    historial_repo = MagicMock()
    historial_repo.guardar = AsyncMock(side_effect=_guardar)
    return pipeline, historial_repo, saved


@pytest.mark.asyncio
async def test_recuperar_contexto_persiste_historial() -> None:
    """El use case persiste el resultado en consulta_historial (D9)."""
    pipeline, historial_repo, saved = _make_dependencies()
    req = ConsultaRequest(consulta="plazo de apelacion?", usuario_id=1)

    result = await ejecutar(req, pipeline, historial_repo)

    assert isinstance(result, ResultadoConsulta)
    assert result.historial_id == 99
    assert historial_repo.guardar.await_count == 1
    assert len(saved) == 1
    assert saved[0].pregunta == "plazo de apelacion?"
    assert saved[0].usuario_id == 1
    assert saved[0].tipo_respuesta == "consulta_simple"
    assert saved[0].latencia_ms == 123


@pytest.mark.asyncio
async def test_recuperar_contexto_respuesta_es_null_en_sprint3() -> None:
    """D11: respuesta es NULL en Sprint 3 (la LLM llega en Sprint 6)."""
    pipeline, historial_repo, saved = _make_dependencies()
    req = ConsultaRequest(consulta="x", usuario_id=1)

    await ejecutar(req, pipeline, historial_repo)

    assert saved[0].respuesta is None
    assert saved[0].modelo_llm is None


@pytest.mark.asyncio
async def test_recuperar_contexto_devuelve_contexto_al_caller() -> None:
    """El caller recibe el ContextoRecuperado en el ResultadoConsulta."""
    pipeline, historial_repo, _ = _make_dependencies()
    req = ConsultaRequest(consulta="x", usuario_id=1)

    result = await ejecutar(req, pipeline, historial_repo)

    assert result.contexto.query_original == "plazo de apelacion?"
    assert len(result.contexto.fragmentos) == 2
    assert list(result.contexto.scores) == [0.9, 0.7]


@pytest.mark.asyncio
async def test_recuperar_contexto_serializa_fuentes_jsonb() -> None:
    """fuentes_recuperadas se persiste como dict JSONB-compatible."""
    pipeline, historial_repo, saved = _make_dependencies()
    req = ConsultaRequest(consulta="x", usuario_id=1, expediente_id=42)

    await ejecutar(req, pipeline, historial_repo)

    fuentes = saved[0].fuentes_recuperadas
    assert isinstance(fuentes, dict)
    assert fuentes["tipo_respuesta"] == "consulta_simple"
    assert fuentes["expediente_id"] is None  # el contexto es consulta_simple sin expte
    assert fuentes["fragmentos_count"] == 2
    assert fuentes["scores"] == [0.9, 0.7]
    assert isinstance(fuentes["fragmentos"], list)
    assert fuentes["fragmentos"][0]["qdrant_point_id"] == "a"


@pytest.mark.asyncio
async def test_recuperar_contexto_propagates_consulta_sin_expediente() -> None:
    """ConsultaSinExpedienteError del pipeline se propaga."""
    pipeline = MagicMock()
    from src.domain.exceptions import ConsultaSinExpedienteError

    pipeline.ejecutar = AsyncMock(side_effect=ConsultaSinExpedienteError("requiere"))
    historial_repo = MagicMock()

    req = ConsultaRequest(consulta="auto de vista", usuario_id=1, expediente_id=None)
    with pytest.raises(ConsultaSinExpedienteError):
        await ejecutar(req, pipeline, historial_repo)
    historial_repo.guardar.assert_not_called()


@pytest.mark.asyncio
async def test_recuperar_contexto_serializa_contexto_expandido_latencia_total() -> None:
    """Regresión FIX 2: latencia_ms del JSONB debe ser la total del pipeline,
    no solo la de Fase 4 (expansion). ContextoExpandido.latencia_ms se
    propaga desde el ContextoRecuperado original que entró al expansor.
    """
    saved: list[ConsultaHistorial] = []
    trazabilidad = TrazabilidadPipeline(
        latencia_busqueda_ms=0,
        latencia_reranking_ms=0,
        latencia_expansion_ms=42,  # solo Fase 4
        nodos_ascendidos=3,
        fragmentos_originales_count=2,
        fragmentos_expandidos_count=5,
        breadcrumbs_count=4,
        expansion_realizada=True,
    )
    contexto_expandido = ContextoExpandido(
        fragmentos_con_padres=(_frag("a"), _frag("b")),
        scores=(0.9, 0.7),
        query_original="plazo de apelacion?",
        tipo_respuesta="consulta_simple",
        expediente_id=None,
        latencia_ms=142,  # latencia TOTAL (fases 1-3 + Fase 4)
        trazabilidad=trazabilidad,
    )

    pipeline = MagicMock()
    pipeline.ejecutar = AsyncMock(return_value=contexto_expandido)

    async def _guardar(historial: ConsultaHistorial) -> ConsultaHistorial:
        historial.id = 99
        historial.created_at = datetime(2026, 8, 4)
        saved.append(historial)
        return historial

    historial_repo = MagicMock()
    historial_repo.guardar = AsyncMock(side_effect=_guardar)

    req = ConsultaRequest(consulta="plazo de apelacion?", usuario_id=1)
    await ejecutar(req, pipeline, historial_repo)

    fuentes = saved[0].fuentes_recuperadas
    assert fuentes["latencia_ms"] == 142, (
        "latencia_ms debe ser la total del pipeline, no solo expansion"
    )
    assert fuentes["expansion"]["latencia_expansion_ms"] == 42
    assert fuentes["expansion"]["realizada"] is True
    assert fuentes["expansion"]["nodos_ascendidos"] == 3
    assert saved[0].latencia_ms == 142
