"""Tests F2.2: jurisprudencia como norma (colección separada + fan-out).

- IndexarNorma rutea SCP-*/CIDH-* al repo de jurisprudencia con payload N2
  (tipo_fuente, numero_sentencia, organo, bloque, nivel_autoridad).
- HybridSearcher hace fan-out a la colección `jurisprudencia` sin filtros
  de expediente (globales, como normas) pero con usuario_id (Regla 4).
- QdrantJurisprudenciaRepo usa su colección e índices N2.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.corpus.indexar_norma import IndexarNorma, IndexarNormaRequest
from src.application.services.hybrid_searcher import HybridSearcher
from src.domain.entities.fragmento import Fragmento
from src.domain.services.segmentacion.base import (
    ArbolJerarquico,
    FragmentoProducible,
)
from src.domain.value_objects import ScoredPoint


def _repos_base():
    extractor = MagicMock()
    extractor.extract = AsyncMock(side_effect=AssertionError("no debe extraer"))
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1] * 4])
    vector_repo = MagicMock()
    vector_repo._collection_has_sparse = MagicMock(return_value=False)
    vector_repo.upsert_corpus = AsyncMock()
    vector_repo_juris = MagicMock()
    vector_repo_juris._collection_has_sparse = MagicMock(return_value=False)
    vector_repo_juris.upsert_corpus = AsyncMock()
    norma_repo = MagicMock()

    async def _save(norma):
        norma.id = 9
        return norma

    norma_repo.save = AsyncMock(side_effect=_save)
    norma_repo.marcar_indexada = AsyncMock()
    fragmento_repo = MagicMock()
    fragmento_repo.save_many = AsyncMock(side_effect=lambda frags: frags)
    return extractor, embedder, vector_repo, vector_repo_juris, norma_repo, fragmento_repo


def _segmentador_fallo():
    from src.domain.services.segmentacion import registro

    segmentador = MagicMock()
    segmentador.segmentar = MagicMock(
        return_value=ArbolJerarquico(
            abreviatura="SCP-0623-2024-S4",
            raices=[],
            nodos={},
            fragmentos=[
                FragmentoProducible(
                    texto="La negación de prueba vulnera la defensa.",
                    nivel_jerarquico=4,
                    tipo_chunk="fundamento_de_derecho_analisis",
                    padre_ref_key="SCP-0623-2024-S4_DERECHO_III-1",
                    metadatos={
                        "bloque": "derecho",
                        "numero_sentencia": "SCP-0623-2024-S4",
                    },
                ),
            ],
        )
    )
    orig = registro.SegmentadorRegistry.obtener
    registro.SegmentadorRegistry.obtener = classmethod(lambda cls, abrev: segmentador)
    return orig


@pytest.mark.asyncio
async def test_indexar_scp_usa_coleccion_jurisprudencia_y_payload_n2() -> None:
    """SCP-* -> repo jurisprudencia, payload N2, colección en respuesta."""
    from src.domain.services.segmentacion import registro

    ext, emb, vec, vec_j, nrepo, frepo = _repos_base()
    orig = _segmentador_fallo()
    try:
        uc = IndexarNorma(
            text_extractor=ext,
            embedder=emb,
            vector_repo=vec,
            norma_repo=nrepo,
            fragmento_repo=frepo,
            vector_repo_jurisprudencia=vec_j,
        )
        result = await uc.ejecutar(
            IndexarNormaRequest(
                abreviatura="SCP-0623-2024-S4",
                ruta_pdf="/tmp/x.txt",
                texto_directo="I. ANTECEDENTES...",
            )
        )
    finally:
        registro.SegmentadorRegistry.obtener = orig

    vec.upsert_corpus.assert_not_called()
    vec_j.upsert_corpus.assert_awaited_once()
    puntos = vec_j.upsert_corpus.await_args.args[0]
    assert len(puntos) == 1
    payload = puntos[0]["payload"]
    assert payload["tipo_fuente"] == "jurisprudencia"
    assert payload["numero_sentencia"] == "SCP-0623-2024-S4"
    assert payload["organo"] == "TCP"
    assert payload["bloque"] == "derecho"
    assert payload["nivel_autoridad"] == "vinculante"
    assert result.qdrant_collection == "jurisprudencia"
    # Norma PG con tipo/jerarquía de jurisprudencia.
    norma_guardada = nrepo.save.await_args.args[0]
    assert norma_guardada.tipo == "scp_tcp"
    assert norma_guardada.jerarquia == "jurisprudencia"


@pytest.mark.asyncio
async def test_indexar_ley_sigue_en_corpus_juridico() -> None:
    """Sin repo N2 o abreviatura de ley: todo como antes (compat)."""
    from src.domain.services.segmentacion import registro

    ext, emb, vec, _vec_j, nrepo, frepo = _repos_base()
    orig = _segmentador_fallo()
    try:
        uc = IndexarNorma(
            text_extractor=ext,
            embedder=emb,
            vector_repo=vec,
            norma_repo=nrepo,
            fragmento_repo=frepo,
        )
        result = await uc.ejecutar(
            IndexarNormaRequest(
                abreviatura="SCP-0623-2024-S4",
                ruta_pdf="/tmp/x.txt",
                texto_directo="I. ANTECEDENTES...",
            )
        )
    finally:
        registro.SegmentadorRegistry.obtener = orig

    # Sin repo N2 inyectado: cae al repo principal (degradación segura).
    vec.upsert_corpus.assert_awaited_once()
    assert result.qdrant_collection == "corpus_juridico"


def _searcher_con_n2(
    puntos_main: list[ScoredPoint], puntos_n2: list[ScoredPoint]
) -> tuple[HybridSearcher, MagicMock, MagicMock]:
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1] * 768])
    corpus_repo = MagicMock()
    corpus_repo.search_hybrid = AsyncMock(return_value=puntos_main)
    juris_repo = MagicMock()
    juris_repo.search_hybrid = AsyncMock(return_value=puntos_n2)
    fragmento_repo = MagicMock()
    fragmento_repo.get_by_qdrant_ids = AsyncMock(return_value=[])
    fragmento_repo.listar_vocabulario = AsyncMock(return_value=None)
    config_repo = MagicMock()
    config_repo.get_config = AsyncMock(
        return_value=MagicMock(score_threshold=0.0, normalizar_query=True)
    )
    searcher = HybridSearcher(
        embedder=embedder,
        corpus_repo=corpus_repo,
        fragmento_repo=fragmento_repo,
        config=config_repo,
        jurisprudencia_repo=juris_repo,
    )
    return searcher, corpus_repo, juris_repo


@pytest.mark.asyncio
async def test_fanout_n2_sin_filtros_expediente_con_usuario() -> None:
    """El pase N2 no lleva expediente_id/obra_ids pero sí usuario_id (R4)."""
    searcher, _corpus, juris = _searcher_con_n2([], [])
    await searcher.buscar(
        query="nulidad de oficio",
        usuario_id=26,
        filtros={"expediente_id": "8", "obra_ids": [1]},
        top_k_denso=5,
        top_k_lexico=5,
    )
    filtros_n2 = juris.search_hybrid.await_args.kwargs["filters"]
    assert "expediente_id" not in filtros_n2
    assert "obra_ids" not in filtros_n2
    assert filtros_n2["usuario_id"] == 26


@pytest.mark.asyncio
async def test_fanout_n2_fusiona_por_max_score() -> None:
    """Candidatos de ambas colecciones se fusionan (max) e hidratan de PG."""
    searcher, _corpus, _juris = _searcher_con_n2(
        [ScoredPoint(qdrant_id="ley-1", score=0.9, payload={})],
        [ScoredPoint(qdrant_id="scp-1", score=0.8, payload={})],
    )
    frag_ley = Fragmento(
        id=1,
        norma_id=1,
        obra_id=None,
        expediente_id=None,
        qdrant_point_id="ley-1",
        texto="art",
        padre_ref_id=None,
        padre_ref_key=None,
        nivel_jerarquico=4,
        metadatos=None,
        tipo_chunk="articulo_simple",
    )
    frag_scp = Fragmento(
        id=2,
        norma_id=9,
        obra_id=None,
        expediente_id=None,
        qdrant_point_id="scp-1",
        texto="ratio",
        padre_ref_id=None,
        padre_ref_key=None,
        nivel_jerarquico=4,
        metadatos=None,
        tipo_chunk="fundamento_de_derecho_analisis",
    )
    searcher._fragmento_repo.get_by_qdrant_ids = AsyncMock(return_value=[frag_ley, frag_scp])
    resultado = await searcher.buscar(
        query="debido proceso",
        usuario_id=26,
        filtros={},
        top_k_denso=5,
        top_k_lexico=5,
    )
    assert [f.qdrant_point_id for f, _ in resultado] == ["ley-1", "scp-1"]


def test_repo_jurisprudencia_coleccion_e_indices() -> None:
    """Subclase: colección propia + índices N2 (sin tocar la base)."""
    from src.adapters.qdrant.qdrant_jurisprudencia_repo import (
        QdrantJurisprudenciaRepo,
    )

    assert QdrantJurisprudenciaRepo.COLLECTION_NAME == "jurisprudencia"
    repo = QdrantJurisprudenciaRepo.__new__(QdrantJurisprudenciaRepo)
    repo._client = MagicMock()
    orig_base = QdrantJurisprudenciaRepo.__bases__[0]._create_payload_indexes
    llamadas: list[str] = []
    QdrantJurisprudenciaRepo.__bases__[0]._create_payload_indexes = lambda self: llamadas.append(
        "base"
    )
    try:
        repo._create_payload_indexes()
    finally:
        QdrantJurisprudenciaRepo.__bases__[0]._create_payload_indexes = orig_base
    assert llamadas == ["base"]
    campos = [c.kwargs["field_name"] for c in repo._client.create_payload_index.call_args_list]
    for esperado in (
        "numero_sentencia",
        "organo",
        "bloque",
        "nivel_autoridad",
    ):
        assert esperado in campos
