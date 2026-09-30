"""Cobertura de obras del expediente: cupo de jurisprudencia y diversidad por obra.

Bug (diagnostico-cobertura): la fusión RRF alternaba obrado / jurisprudencia /
doctrina y la jurisprudencia ocupaba ~41 % del top 15 aun preguntando por el caso;
y una obra con muchos fragmentos llenaba el pozo y dejaba afuera a las demás (exp13).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.services.hybrid_searcher import HybridSearcher
from src.application.services.pipeline_rag import PipelineRAG
from tests._factories import make_fragmento


def _obra(qid: str, obra_id: int):
    return make_fragmento(qdrant_point_id=qid, norma_id=None, obra_id=obra_id, tipo_chunk=None)


def _jur(qid: str, clave: str = "SCP-X"):
    return make_fragmento(
        qdrant_point_id=qid, tipo_chunk="fundamento_de_hecho", padre_ref_key=clave
    )


def _ids(pares) -> list[str]:
    return [f.qdrant_point_id for f, _ in pares]


def test_cupo_jurisprudencia_recorta_no_explicitos() -> None:
    candidatos = [(_jur(f"j{i}"), 1.0) for i in range(5)] + [(_obra("o", 1), 0.5)]

    PipelineRAG._aplicar_cupo_jurisprudencia(candidatos, set())

    assert _ids(candidatos) == ["j0", "j1", "j2", "o"]


def test_cupo_jurisprudencia_respeta_explicitos() -> None:
    candidatos = [(_jur(f"j{i}"), 1.0) for i in range(4)] + [(_jur("pedida", "SCP-VOCAL"), 0.9)]

    PipelineRAG._aplicar_cupo_jurisprudencia(candidatos, {"SCP-VOCAL"})

    assert _ids(candidatos) == ["j0", "j1", "j2", "pedida"]


def test_diversificar_trae_la_obra_que_quedo_fuera_del_corte() -> None:
    seleccion = [(_obra("a1", 1), 0.9), (_obra("a2", 1), 0.8), (_jur("j"), 0.7)]
    candidatos = [*seleccion, (_obra("b1", 2), 0.5), (_obra("b2", 2), 0.4)]

    out = PipelineRAG._diversificar_obras(seleccion, candidatos)

    # La obra 2 entra con su mejor fragmento, en lugar del repetido de la obra 1.
    assert _ids(out) == ["a1", "b1", "j"]


def test_diversificar_no_reemplaza_normas_ni_la_unica_de_una_obra() -> None:
    norma = make_fragmento(qdrant_point_id="n", norma_id=5, tipo_chunk="articulo_simple")
    seleccion = [(_obra("a1", 1), 0.9), (norma, 0.8)]
    candidatos = [*seleccion, (_obra("b1", 2), 0.5)]

    out = PipelineRAG._diversificar_obras(seleccion, candidatos)

    assert _ids(out) == ["a1", "n"]


@pytest.mark.asyncio
async def test_completar_obras_busca_solo_las_que_faltan_sin_fanout() -> None:
    buscador = MagicMock()
    b1 = _obra("b1", 2)
    buscador.buscar = AsyncMock(return_value=[(b1, 0.3), (_obra("b2", 2), 0.2)])
    obra_repo = SimpleNamespace(
        listar_por_expediente=AsyncMock(
            return_value=[
                SimpleNamespace(id=1, corpus_ref=None),
                SimpleNamespace(id=2, corpus_ref=None),
            ]
        )
    )
    pipeline = PipelineRAG(
        buscador=buscador, reranker_svc=MagicMock(), config_repo=MagicMock(), obra_repo=obra_repo
    )
    candidatos = [(_obra("a1", 1), 0.9)]
    cfg = SimpleNamespace(top_k_denso=10, top_k_lexico=5)

    await pipeline._completar_obras_del_expediente(
        candidatos, "consulta", 7, None, {"expediente_id": "7", "solo_expediente": True}, 26, cfg
    )

    assert _ids(candidatos) == ["a1", "b1"]
    kwargs = buscador.buscar.await_args.kwargs
    assert kwargs["filtros"]["obra_ids"] == [2]
    assert kwargs["con_fanout"] is False


@pytest.mark.asyncio
async def test_buscar_sin_fanout_no_consulta_colecciones_extra() -> None:
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1]])
    corpus = MagicMock()
    corpus.search_hybrid = AsyncMock(return_value=[])
    extra = MagicMock()
    extra.search_hybrid = AsyncMock(return_value=[])
    fragmentos = MagicMock()
    fragmentos.listar_vocabulario = AsyncMock(return_value=frozenset())
    config = MagicMock()
    config.get_config = AsyncMock(
        return_value=SimpleNamespace(normalizar_query=False, score_threshold=0.7)
    )
    buscador = HybridSearcher(
        embedder=embedder,
        corpus_repo=corpus,
        fragmento_repo=fragmentos,
        config=config,
        jurisprudencia_repo=extra,
    )

    await buscador.buscar(
        query="q", usuario_id=1, filtros={}, top_k_denso=10, top_k_lexico=5, con_fanout=False
    )

    extra.search_hybrid.assert_not_awaited()
