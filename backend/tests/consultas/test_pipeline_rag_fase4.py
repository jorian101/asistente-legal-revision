"""Tests de PipelineRAG Fase 4 — expansion jerarquica (Sprint 5).

Cubre:
- Con expansor: ejecutar retorna ContextoExpandido.
- Sin expansor: degrada a ContextoRecuperado (backward compat Sprint 3).
- expandir=False: no ejecuta Fase 4 aun con expansor configurado.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.services.hybrid_searcher import HybridSearcher
from src.application.services.pipeline_rag import PipelineRAG
from src.application.services.reranker_service import RerankerService
from src.domain.entities.fragmento import Fragmento
from src.domain.value_objects.contexto_expandido import ContextoExpandido
from src.domain.value_objects.contexto_recuperado import ContextoRecuperado


def _frag(qid: str) -> Fragmento:
    return Fragmento(
        id=1,
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


def _make_pipeline(
    *,
    candidatos: list[tuple[Fragmento, float]],
    rerankeados: list[tuple[Fragmento, float]],
    expansor: object | None = None,
) -> PipelineRAG:
    buscador = MagicMock(spec=HybridSearcher)
    buscador.buscar = AsyncMock(return_value=candidatos)

    reranker = MagicMock(spec=RerankerService)
    reranker.aplicar = AsyncMock(return_value=rerankeados)

    config_repo = MagicMock()
    config_repo.get_config = AsyncMock(
        return_value=MagicMock(top_k_denso=40, top_k_lexico=20, top_k_final=7)
    )

    return PipelineRAG(
        buscador=buscador,
        reranker_svc=reranker,
        config_repo=config_repo,
        expansor=expansor,
    )


def _make_expansor_mock(contexto_expandido: ContextoExpandido) -> MagicMock:
    expansor = MagicMock()
    expansor.expandir = AsyncMock(return_value=contexto_expandido)
    return expansor


@pytest.mark.asyncio
async def test_pipeline_con_expansor_retorna_contexto_expandido() -> None:
    """Fase 4 con expansor configurado -> ContextoExpandido."""
    frag = _frag("qdrant-1")
    candidatos = [(frag, 0.9)]
    rerankeados = [(frag, 0.95)]

    contexto_expandido = ContextoExpandido(
        fragmentos_con_padres=(frag,),
        scores=(0.95,),
        query_original="test query",
        tipo_respuesta="consulta_simple",
        expediente_id=None,
        breadcrumbs=(("ROOT", "N1"),),
        trazabilidad=None,
    )
    expansor = _make_expansor_mock(contexto_expandido)

    pipeline = _make_pipeline(
        candidatos=candidatos,
        rerankeados=rerankeados,
        expansor=expansor,
    )

    resultado = await pipeline.ejecutar(
        consulta="test query",
        usuario_id=1,
        expediente_id=None,
        expandir=True,
    )

    assert isinstance(resultado, ContextoExpandido)
    assert resultado.breadcrumbs == (("ROOT", "N1"),)
    expansor.expandir.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_sin_expansor_degrada_a_contexto_recuperado() -> None:
    """Sin expansor (None) -> ContextoRecuperado (backward compat Sprint 3)."""
    frag = _frag("qdrant-1")
    candidatos = [(frag, 0.9)]
    rerankeados = [(frag, 0.95)]

    pipeline = _make_pipeline(
        candidatos=candidatos,
        rerankeados=rerankeados,
        expansor=None,
    )

    resultado = await pipeline.ejecutar(
        consulta="test query",
        usuario_id=1,
        expediente_id=None,
        expandir=True,
    )

    assert isinstance(resultado, ContextoRecuperado)
    assert not isinstance(resultado, ContextoExpandido)
    assert resultado.fragmentos == (frag,)


@pytest.mark.asyncio
async def test_pipeline_expandir_false_no_ejecuta_fase4() -> None:
    """expandir=False + expansor configurado -> resuelve breadcrumbs, NO expandir.

    G6 (commit 0c4abb9): con expandir=False el pipeline llama
    ExpansorContexto.resolver_breadcrumbs() (breadcrumbs livianos sin subir
    padres) en vez de expandir() (expansion completa).
    """
    frag = _frag("qdrant-1")
    candidatos = [(frag, 0.9)]
    rerankeados = [(frag, 0.95)]

    contexto_expandido = ContextoExpandido(
        fragmentos_con_padres=(frag,),
        scores=(0.95,),
        query_original="test query",
        tipo_respuesta="consulta_simple",
        expediente_id=None,
        breadcrumbs=(("ROOT", "qdrant-1"),),
        trazabilidad=None,
    )
    expansor = _make_expansor_mock(contexto_expandido)
    # G6: el expansor ahora tambien expone resolver_breadcrumbs
    expansor.resolver_breadcrumbs = AsyncMock(return_value=contexto_expandido)

    pipeline = _make_pipeline(
        candidatos=candidatos,
        rerankeados=rerankeados,
        expansor=expansor,
    )

    resultado = await pipeline.ejecutar(
        consulta="test query",
        usuario_id=1,
        expediente_id=None,
        expandir=False,
    )

    # No se ejecuta la expansion completa, pero si la resolucion de breadcrumbs
    expansor.expandir.assert_not_awaited()
    expansor.resolver_breadcrumbs.assert_awaited_once()
    assert isinstance(resultado, ContextoExpandido)
    assert resultado.breadcrumbs == (("ROOT", "qdrant-1"),)
