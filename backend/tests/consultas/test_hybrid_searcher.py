"""Tests de HybridSearcher (Fase 2 del pipeline RAG) — Regla 4 BLOQUEANTE.

Cubre:
- usuario_id ausente -> TypeError en runtime (sin default, fuerza correctness).
- Fragmentos publicos (corpus) visibles para todos.
- Operador A NO ve fragmentos privados de operador B (Regla 4).
- HybridSearcher embebe la query y llama a corpus_repo.search_hybrid.
- Score threshold de configuracion_rag filtra los resultados.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.services.hybrid_searcher import HybridSearcher
from src.domain.entities.fragmento import Fragmento
from src.domain.value_objects import ScoredPoint


def _make_searcher(
    *,
    scored_points: list[ScoredPoint],
    fragmentos: list[Fragmento],
    config_threshold: float = 0.0,
) -> HybridSearcher:
    """Construye un HybridSearcher con mocks de sus 4 puertos."""
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1] * 768])

    corpus_repo = MagicMock()
    corpus_repo.search_hybrid = AsyncMock(return_value=scored_points)

    fragmento_repo = MagicMock()
    fragmento_repo.get_by_qdrant_ids = AsyncMock(return_value=fragmentos)
    # Capa A: sin vocabulario (None) -> el searcher usa el dict minimo.
    fragmento_repo.listar_vocabulario = AsyncMock(return_value=None)

    config_repo = MagicMock()
    config_repo.get_config = AsyncMock(
        return_value=MagicMock(score_threshold=config_threshold, normalizar_query=True)
    )

    return HybridSearcher(
        embedder=embedder,
        corpus_repo=corpus_repo,
        fragmento_repo=fragmento_repo,
        config=config_repo,
    )


def _scored(qid: str, score: float) -> ScoredPoint:
    return ScoredPoint(qdrant_id=qid, score=score, payload={})


def _fragmento(qid: str, **overrides) -> Fragmento:
    return Fragmento(
        id=overrides.get("id"),
        norma_id=overrides.get("norma_id", 1),
        obra_id=overrides.get("obra_id"),
        expediente_id=overrides.get("expediente_id"),
        qdrant_point_id=qid,
        texto=overrides.get("texto", "..."),
        padre_ref_id=overrides.get("padre_ref_id"),
        padre_ref_key=overrides.get("padre_ref_key"),
        nivel_jerarquico=overrides.get("nivel_jerarquico", 4),
        metadatos=overrides.get("metadatos"),
        tipo_chunk=overrides.get("tipo_chunk", "articulo_simple"),
    )


@pytest.mark.asyncio
async def test_raises_if_usuario_id_missing() -> None:
    """Regla 4 (BLOQUEANTE): usuario_id sin default -> TypeError explicito.

    La firma `usuario_id: int` sin default es a proposito (D5): fuerza
    al caller a proveerlo. Si lo pasa por keyword vacio o None, falla.
    """
    searcher = _make_searcher(
        scored_points=[_scored("a", 0.9)],
        fragmentos=[_fragmento("a")],
    )
    with pytest.raises(TypeError):
        await searcher.buscar(
            query="algo",
            usuario_id=None,  # type: ignore[arg-type]
            filtros={},
            top_k_denso=10,
            top_k_lexico=5,
        )


@pytest.mark.asyncio
async def test_fragmentos_publicos_visibles_para_todos() -> None:
    """Fragmentos del corpus (visibilidad vacia) son visibles para todos.

    El adapter Qdrant construye un should con IsEmptyCondition(visibilidad)
    que matchea fragmentos del corpus juridico (normas).
    """
    f1 = _fragmento("qid-1")
    f2 = _fragmento("qid-2")
    scored = [_scored("qid-1", 0.9), _scored("qid-2", 0.7)]

    searcher = _make_searcher(scored_points=scored, fragmentos=[f1, f2])

    # Dos usuarios distintos ven el mismo corpus publico.
    out_a = await searcher.buscar(
        query="desobediencia",
        usuario_id=10,
        filtros={},
        top_k_denso=10,
        top_k_lexico=5,
    )
    out_b = await searcher.buscar(
        query="desobediencia",
        usuario_id=20,
        filtros={},
        top_k_denso=10,
        top_k_lexico=5,
    )

    assert [f.qdrant_point_id for f, _ in out_a] == ["qid-1", "qid-2"]
    assert [f.qdrant_point_id for f, _ in out_b] == ["qid-1", "qid-2"]
    # Ambos Qdrant calls llevan usuario_id distinto en el filtro (defensa).
    assert searcher._corpus_repo.search_hybrid.await_count == 2
    calls = searcher._corpus_repo.search_hybrid.await_args_list
    assert calls[0].kwargs["filters"]["usuario_id"] == 10
    assert calls[1].kwargs["filters"]["usuario_id"] == 20


@pytest.mark.asyncio
async def test_operador_a_no_ve_fragmentos_privados_de_operador_b() -> None:
    """El filtro de privacidad del adapter (Regla 4) se aplica.

    Este test verifica que HybridSearcher PASA el usuario_id al adapter y
    que el adapter aplica el filtro. La exclusion real de obras privadas
    de otro se valida en el test del adapter Qdrant (test_hybrid_search).
    Aqui verificamos que el filtro de Qdrant contiene el usuario correcto.
    """
    scored = [_scored("privado-de-A", 0.95)]
    fragmentos = [_fragmento("privado-de-A")]
    searcher = _make_searcher(scored_points=scored, fragmentos=fragmentos)

    await searcher.buscar(
        query="apelar",
        usuario_id=10,  # Operador A
        filtros={"expediente_id": 99},
        top_k_denso=10,
        top_k_lexico=5,
    )

    call = searcher._corpus_repo.search_hybrid.await_args
    assert call is not None
    filters = call.kwargs["filters"]
    # El filtro que se manda a Qdrant DEBE llevar usuario_id=10.
    assert filters["usuario_id"] == 10
    assert filters["expediente_id"] == 99


@pytest.mark.asyncio
async def test_score_threshold_filter() -> None:
    """Resultados con score < score_threshold son filtrados por el servicio."""
    fragmentos = [_fragmento("p1"), _fragmento("p2")]
    scored = [_scored("p1", 0.5), _scored("p2", 0.9)]

    searcher = _make_searcher(
        scored_points=scored,
        fragmentos=fragmentos,
        config_threshold=0.7,  # filtra p1 (0.5)
    )

    out = await searcher.buscar(
        query="x",
        usuario_id=1,
        filtros={},
        top_k_denso=10,
        top_k_lexico=5,
    )

    assert [f.qdrant_point_id for f, _ in out] == ["p2"]


@pytest.mark.asyncio
async def test_embeds_query_and_calls_search_hybrid() -> None:
    """HybridSearcher embebe la query y llama search_hybrid con filtros."""
    searcher = _make_searcher(
        scored_points=[],
        fragmentos=[],
    )

    await searcher.buscar(
        query="Cual es el plazo de apelacion?",
        usuario_id=1,
        filtros={"abreviatura": "CPPM"},
        top_k_denso=40,
        top_k_lexico=20,
    )

    # Embed fue llamado con la query NORMALIZADA (Fase 1 — se quitan
    # muletillas "cual es el" que ensucian el embedding denso).
    embed_call = searcher._embedder.embed.await_args
    assert embed_call is not None
    assert embed_call.args[0] == ["plazo de apelacion?"]

    # search_hybrid fue llamado con limit = top_k_denso + top_k_lexico.
    search_call = searcher._corpus_repo.search_hybrid.await_args
    assert search_call.kwargs["limit"] == 60  # 40 + 20


@pytest.mark.asyncio
async def test_embed_usa_query_normalizada_sin_saludo() -> None:
    """Fase 1: saludo+muletilla se limpian antes del embedding (bug sala).

    La query "hola cual es el prinincipio del debido proceso" se normaliza a
    "principio del debido proceso" para la busqueda, sin alterar el texto
    visible (el LLM sigue recibiendo la query original).
    """
    searcher = _make_searcher(scored_points=[], fragmentos=[])

    await searcher.buscar(
        query="hola cual es el prinincipio del debido proceso",
        usuario_id=1,
        filtros={},
        top_k_denso=10,
        top_k_lexico=5,
    )

    embed_call = searcher._embedder.embed.await_args
    assert embed_call is not None
    assert embed_call.args[0] == ["principio del debido proceso"]


@pytest.mark.asyncio
async def test_embed_usa_vocabulario_del_corpus_para_typos() -> None:
    """Capa A: el typo se corrige contra el vocabulario real del corpus.

    El searcher llama listar_vocabulario (cacheado por proceso) y lo pasa a
    normalizar_query. La query con typo "prinincipio" se corrige a
    "principio" antes del embedding.
    """
    searcher = _make_searcher(scored_points=[], fragmentos=[])
    searcher._fragmento_repo.listar_vocabulario = AsyncMock(
        return_value=frozenset({"principio", "debido", "proceso", "penal"})
    )

    await searcher.buscar(
        query="hola cual es el prinincipio del debido proceso",
        usuario_id=1,
        filtros={},
        top_k_denso=10,
        top_k_lexico=5,
    )

    embed_call = searcher._embedder.embed.await_args
    assert embed_call is not None
    assert embed_call.args[0] == ["principio del debido proceso"]


@pytest.mark.asyncio
async def test_degrada_a_dict_si_vocabulario_falla() -> None:
    """Capa A: si listar_vocabulario falla, no rompe la busqueda.

    El searcher degrada a None (dict minimo de typos) y sigue normalizando
    los prefijos. Nunca bloquea la consulta.
    """
    searcher = _make_searcher(scored_points=[], fragmentos=[])
    searcher._fragmento_repo.listar_vocabulario = AsyncMock(side_effect=RuntimeError("bd caida"))

    await searcher.buscar(
        query="hola cual es el prinincipio del debido proceso",
        usuario_id=1,
        filtros={},
        top_k_denso=10,
        top_k_lexico=5,
    )

    embed_call = searcher._embedder.embed.await_args
    assert embed_call is not None
    assert embed_call.args[0] == ["principio del debido proceso"]


@pytest.mark.asyncio
async def test_toggle_desactivado_usa_query_cruda() -> None:
    """Capa A2: si normalizar_query=False (admin), se usa la query tal cual.

    Con el toggle desactivado, ni saludos ni typos se limpian: el embedding
    recibe la query cruda del usuario.
    """
    searcher = _make_searcher(scored_points=[], fragmentos=[])
    searcher._config.get_config = AsyncMock(
        return_value=MagicMock(score_threshold=0.0, normalizar_query=False)
    )

    await searcher.buscar(
        query="hola cual es el prinincipio del debido proceso",
        usuario_id=1,
        filtros={},
        top_k_denso=10,
        top_k_lexico=5,
    )

    embed_call = searcher._embedder.embed.await_args
    assert embed_call is not None
    assert embed_call.args[0] == ["hola cual es el prinincipio del debido proceso"]


@pytest.mark.asyncio
async def test_skips_qdrant_results_missing_in_pg() -> None:
    """Si Qdrant devuelve IDs que no existen en PG, se omiten silenciosamente."""
    scored = [_scored("existe", 0.9), _scored("no-en-pg", 0.8)]
    fragmentos = [_fragmento("existe")]  # solo 'existe' esta en PG

    searcher = _make_searcher(scored_points=scored, fragmentos=fragmentos)

    out = await searcher.buscar(
        query="x",
        usuario_id=1,
        filtros={},
        top_k_denso=10,
        top_k_lexico=5,
    )

    assert [f.qdrant_point_id for f, _ in out] == ["existe"]


@pytest.mark.asyncio
async def test_queries_extra_embebe_y_fusiona_con_dedupe() -> None:
    """P3: queries_extra (query, filtros) se embeben y fusionan por qdrant_id.

    - embed es llamado con [query] y con las queries de competencia.
    - search_hybrid se llama una vez por query (principal + 1 competencia).
    - Si un mismo qdrant_id aparece en dos queries, se conserva el mejor score.
    - Los puntos de competencia se fusionan SIN umbral (recuperacion explicita).
    """

    # 1er call (query principal) -> p1=0.8, p2=0.9
    # 2do call (query competencia) -> p2=0.95 (mejor), p3=0.7
    def _side_effect(**kwargs):
        calls = getattr(_side_effect, "_n", 0)
        _side_effect._n = calls + 1
        if calls == 0:
            return [_scored("p1", 0.8), _scored("p2", 0.9)]
        return [_scored("p2", 0.95), _scored("p3", 0.7)]

    searcher = _make_searcher(
        scored_points=[],
        fragmentos=[],
        config_threshold=0.9,  # umbral alto: solo la competencia debe pasar
    )
    searcher._corpus_repo.search_hybrid = AsyncMock(side_effect=_side_effect)
    searcher._fragmento_repo.get_by_qdrant_ids = AsyncMock(
        return_value=[_fragmento("p1"), _fragmento("p2"), _fragmento("p3")]
    )

    out = await searcher.buscar(
        query="uso de documentos falsos",
        usuario_id=1,
        filtros={},
        top_k_denso=10,
        top_k_lexico=5,
        queries_extra=(
            (
                "consulta de oficio articulo 194 codigo de procedimiento penal militar",
                {"abreviatura": "CPPM", "numero_articulo": 194},
            ),
        ),
    )

    # embed llamado 2 veces: [query] y [query_competencia]
    assert searcher._embedder.embed.await_count == 2
    primer_embed = searcher._embedder.embed.await_args_list[0]
    assert primer_embed.args[0] == ["uso de documentos falsos"]
    segundo_embed = searcher._embedder.embed.await_args_list[1]
    assert "194" in segundo_embed.args[0][0]

    # 2 llamadas a search_hybrid (principal + competencia)
    assert searcher._corpus_repo.search_hybrid.await_count == 2

    # La query de competencia lleva el filtro de payload + usuario_id (Regla 4)
    call_comp = searcher._corpus_repo.search_hybrid.await_args_list[1]
    assert call_comp.kwargs["filters"]["abreviatura"] == "CPPM"
    assert call_comp.kwargs["filters"]["numero_articulo"] == 194
    assert call_comp.kwargs["filters"]["usuario_id"] == 1

    # Fusion: p2 conserva 0.95; p1=0.8 (<0.9 umbral) NO pasa; p3=0.7 es
    # competencia -> pasa SIN umbral. Orden por score desc.
    assert [(f.qdrant_point_id, s) for f, s in out] == [("p2", 0.95), ("p3", 0.7)]


@pytest.mark.asyncio
async def test_queries_extra_vacio_comportamiento_original() -> None:
    """queries_extra vacio (default) == comportamiento original (1 query)."""
    scored = [_scored("p1", 0.9)]
    searcher = _make_searcher(scored_points=scored, fragmentos=[_fragmento("p1")])

    await searcher.buscar(
        query="plazo apelacion",
        usuario_id=1,
        filtros={},
        top_k_denso=10,
        top_k_lexico=5,
    )

    embed_call = searcher._embedder.embed.await_args
    assert embed_call is not None
    assert embed_call.args[0] == ["plazo apelacion"]
    assert searcher._corpus_repo.search_hybrid.await_count == 1


@pytest.mark.asyncio
async def test_queries_extra_no_heredan_expediente_id() -> None:
    """P5.7: las queries de competencia (normas publicas) NO llevan expediente_id.

    La query principal filtra por expediente (obras, Regla 5), pero la
    competencia (CPM/CPPM) es publica: heredar expediente_id crearia un
    must(expediente_id=X) contradictorio con abreviatura=CPM.
    """
    searcher = _make_searcher(scored_points=[], fragmentos=[])
    searcher._corpus_repo.search_hybrid = AsyncMock(return_value=[])
    searcher._fragmento_repo.get_by_qdrant_ids = AsyncMock(return_value=[])

    def _embed_side(texts):
        return [[0.1] * 768 for _ in texts]

    searcher._embedder.embed = AsyncMock(side_effect=_embed_side)

    await searcher.buscar(
        query="prescripcion de la accion penal",
        usuario_id=4,
        filtros={"expediente_id": 8},
        top_k_denso=10,
        top_k_lexico=5,
        queries_extra=(
            (
                "prescripcion accion penal militar articulos 38 40 44 45 cpm",
                {"abreviatura": "CPM"},
            ),
        ),
    )

    # La query principal lleva expediente_id=8 (obras del expediente).
    call_principal = searcher._corpus_repo.search_hybrid.await_args_list[0]
    assert call_principal.kwargs["filters"]["expediente_id"] == 8

    # La query de competencia NO lleva expediente_id, pero sí usuario_id (Regla 4).
    call_comp = searcher._corpus_repo.search_hybrid.await_args_list[1]
    assert "expediente_id" not in call_comp.kwargs["filters"]
    assert call_comp.kwargs["filters"]["abreviatura"] == "CPM"
    assert call_comp.kwargs["filters"]["usuario_id"] == 4


@pytest.mark.asyncio
async def test_solo_expediente_pasa_filtro_al_corpus_repo() -> None:
    """Regla 5 (borradores): solo_expediente=True se propaga al corpus_repo.

    El adapter Qdrant usa filtro estricto (expediente_id = X) sin la rama
    OR expediente_id IS NULL: la doctrina global no compite con los obrados
    al redactar ANTECEDENTES de dictamenes.
    """
    searcher = _make_searcher(scored_points=[], fragmentos=[])

    await searcher.buscar(
        query="dictamen de radicatoria",
        usuario_id=1,
        filtros={"expediente_id": 13, "solo_expediente": True},
        top_k_denso=40,
        top_k_lexico=20,
    )

    corpus = searcher._corpus_repo  # noqa: SLF001 — white-box de test
    kwargs = corpus.search_hybrid.await_args.kwargs
    assert kwargs["filters"]["solo_expediente"] is True
    assert kwargs["filters"]["expediente_id"] == 13


@pytest.mark.asyncio
async def test_modo_fusion_rrf_no_umbraliza_scores_bajos() -> None:
    """Con coleccion sparse (fusion RRF), los scores de rank-fusion (~0-0.5)
    NO se filtran por score_threshold: se confía en el ranking + top_k_final."""
    scored = [_scored("f1", 0.5), _scored("f2", 0.33)]
    searcher = _make_searcher(
        scored_points=scored,
        fragmentos=[_fragmento("f1"), _fragmento("f2")],
        config_threshold=0.7,
    )
    searcher._corpus_repo.fusion_enabled = MagicMock(return_value=True)
    out = await searcher.buscar(query="x", usuario_id=1, filtros={}, top_k_denso=10, top_k_lexico=5)
    # Ambos sobreviven pese a score < 0.7 porque es fusion RRF.
    assert [f.qdrant_point_id for f, _ in out] == ["f1", "f2"]


@pytest.mark.asyncio
async def test_modo_denso_si_umbraliza() -> None:
    """Sin sparse (degrade a denso, score=coseno) el umbral sí aplica."""
    scored = [_scored("f1", 0.5), _scored("f2", 0.9)]
    searcher = _make_searcher(
        scored_points=scored,
        fragmentos=[_fragmento("f1"), _fragmento("f2")],
        config_threshold=0.7,
    )
    searcher._corpus_repo.fusion_enabled = MagicMock(return_value=False)
    out = await searcher.buscar(query="x", usuario_id=1, filtros={}, top_k_denso=10, top_k_lexico=5)
    assert [f.qdrant_point_id for f, _ in out] == ["f2"]  # f1 (0.5) filtrado


@pytest.mark.asyncio
async def test_fusion_reparte_entre_colecciones_sin_que_una_escala_domine() -> None:
    """Cada colección devuelve RRF propio (escalas incomparables): fusionar por
    max() dejaba a jurisprudencia y doctrina fuera del top. Se fusionan por
    RRF entre listas: el mejor de cada colección compite en igualdad."""
    searcher = _make_searcher(
        scored_points=[_scored("m1", 0.9), _scored("m2", 0.8), _scored("m3", 0.7)],
        fragmentos=[_fragmento(q) for q in ("m1", "m2", "m3", "j1", "j2", "d1")],
    )
    searcher._corpus_repo.fusion_enabled = MagicMock(return_value=True)
    juris = MagicMock()
    juris.search_hybrid = AsyncMock(return_value=[_scored("j1", 0.02), _scored("j2", 0.01)])
    doctrina = MagicMock()
    doctrina.search_hybrid = AsyncMock(return_value=[_scored("d1", 0.01)])
    searcher._repos_extra = [juris, doctrina]

    out = await searcher.buscar(query="x", usuario_id=1, filtros={}, top_k_denso=10, top_k_lexico=5)

    primeros = {f.qdrant_point_id for f, _ in out[:3]}
    assert primeros == {"m1", "j1", "d1"}
    assert {f.qdrant_point_id for f, _ in out} == {"m1", "m2", "m3", "j1", "j2", "d1"}


@pytest.mark.asyncio
async def test_fusion_un_punto_en_varias_listas_sube() -> None:
    """Un artículo pedido por una consulta dirigida Y hallado por la búsqueda
    principal suma ambos rankings."""

    def _side_effect(**kwargs):
        n = getattr(_side_effect, "_n", 0)
        _side_effect._n = n + 1
        if n == 0:
            return [_scored("a", 0.5), _scored("b", 0.4)]
        return [_scored("b", 0.5)]

    searcher = _make_searcher(
        scored_points=[],
        fragmentos=[_fragmento("a"), _fragmento("b")],
    )
    searcher._corpus_repo.search_hybrid = AsyncMock(side_effect=_side_effect)
    searcher._corpus_repo.fusion_enabled = MagicMock(return_value=True)

    out = await searcher.buscar(
        query="x",
        usuario_id=1,
        filtros={},
        top_k_denso=10,
        top_k_lexico=5,
        queries_extra=(("x", {"abreviatura": "CPE", "numero_articulo": 115}),),
    )

    assert [f.qdrant_point_id for f, _ in out] == ["b", "a"]


@pytest.mark.asyncio
async def test_articulo_explicito_pesa_mas_que_el_ruido_semantico() -> None:
    """«artículo 115 de la CPE»: el fragmento pedido debe ir antes que el rank-1
    semántico de la búsqueda principal (peso_rrf de la consulta dirigida)."""

    def _side_effect(**kwargs):
        n = getattr(_side_effect, "_n", 0)
        _side_effect._n = n + 1
        if n == 0:
            return [_scored("ruido", 0.9), _scored("otro", 0.8)]
        assert "peso_rrf" not in kwargs["filters"], "el peso no debe llegar a Qdrant"
        return [_scored("art115", 0.5)]

    searcher = _make_searcher(
        scored_points=[],
        fragmentos=[_fragmento("ruido"), _fragmento("otro"), _fragmento("art115")],
    )
    searcher._corpus_repo.search_hybrid = AsyncMock(side_effect=_side_effect)
    searcher._corpus_repo.fusion_enabled = MagicMock(return_value=True)

    out = await searcher.buscar(
        query="x",
        usuario_id=1,
        filtros={},
        top_k_denso=10,
        top_k_lexico=5,
        queries_extra=(
            ("articulo 115 CPE", {"abreviatura": "CPE", "numero_articulo": 115, "peso_rrf": 3.0}),
        ),
    )

    assert out[0][0].qdrant_point_id == "art115"


def _con_repos_extra(searcher: HybridSearcher):
    juris, doctrina = MagicMock(), MagicMock()
    juris.search_hybrid = AsyncMock(return_value=[])
    doctrina.search_hybrid = AsyncMock(return_value=[])
    searcher._repos_extra = [juris, doctrina]
    return juris, doctrina


@pytest.mark.asyncio
async def test_fan_out_no_recibe_filtros_que_solo_aplican_a_corpus_juridico() -> None:
    """tipo_fuente, abreviatura y solo_expediente son del corpus/obras: en las
    colecciones jurisprudencia/doctrina daban cero resultados."""
    searcher = _make_searcher(scored_points=[], fragmentos=[])
    juris, doctrina = _con_repos_extra(searcher)

    await searcher.buscar(
        query="x",
        usuario_id=1,
        filtros={
            "tipo_fuente": "doctrina",
            "abreviatura": "CPE",
            "solo_expediente": "True",
            "expediente_id": "9",
            "obra_ids": [1],
        },
        top_k_denso=10,
        top_k_lexico=5,
    )

    for repo in (juris, doctrina):
        assert repo.search_hybrid.await_args.kwargs["filters"] == {"usuario_id": 1}


@pytest.mark.asyncio
async def test_puntero_por_abreviatura_tambien_busca_en_jurisprudencia_y_doctrina() -> None:
    """Una sentencia o un libro fijado vive en su coleccion, no en corpus_juridico."""
    searcher = _make_searcher(scored_points=[], fragmentos=[])
    juris, doctrina = _con_repos_extra(searcher)

    await searcher.buscar(
        query="x",
        usuario_id=1,
        filtros={},
        top_k_denso=10,
        top_k_lexico=5,
        queries_extra=(("x", {"abreviatura": "SCP-0663-2025-S2"}),),
    )

    for repo in (juris, doctrina):
        filtros_llamadas = [c.kwargs["filters"] for c in repo.search_hybrid.await_args_list]
        assert {"abreviatura": "SCP-0663-2025-S2", "usuario_id": 1} in filtros_llamadas


@pytest.mark.asyncio
async def test_articulo_exacto_solo_se_busca_en_el_corpus_de_normas() -> None:
    searcher = _make_searcher(scored_points=[], fragmentos=[])
    juris, doctrina = _con_repos_extra(searcher)

    await searcher.buscar(
        query="x",
        usuario_id=1,
        filtros={},
        top_k_denso=10,
        top_k_lexico=5,
        queries_extra=(("x", {"abreviatura": "CPE", "numero_articulo": 115}),),
    )

    for repo in (juris, doctrina):
        assert all(
            "numero_articulo" not in c.kwargs["filters"] for c in repo.search_hybrid.await_args_list
        )
        assert repo.search_hybrid.await_count == 1  # solo la busqueda principal
