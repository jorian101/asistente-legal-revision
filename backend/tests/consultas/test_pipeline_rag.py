"""Tests del orquestador PipelineRAG (fases 1-3 del pipeline).

Cubre el flujo end-to-end con mocks:
- Orquesta clasificar -> buscar -> reranker.
- latencia_ms se setea.
- Pasa la consulta al HybridSearcher y al RerankerService.
- Regla 4: usuario_id llega al buscador.
- Propaga ConsultaSinExpedienteError del clasificador.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.services.hybrid_searcher import HybridSearcher
from src.application.services.pipeline_rag import PipelineRAG
from src.application.services.reranker_service import RerankerService
from src.domain.entities.fragmento import Fragmento
from src.domain.exceptions import ConsultaSinExpedienteError


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


def _make_pipeline(
    *,
    candidatos: list[tuple[Fragmento, float]],
    rerankeados: list[tuple[Fragmento, float]],
) -> PipelineRAG:
    buscador = MagicMock(spec=HybridSearcher)
    buscador.buscar = AsyncMock(return_value=candidatos)

    reranker = MagicMock(spec=RerankerService)
    reranker.aplicar = AsyncMock(return_value=rerankeados)

    config_repo = MagicMock()
    config_repo.get_config = AsyncMock(
        return_value=MagicMock(top_k_denso=40, top_k_lexico=20, top_k_final=7)
    )

    return PipelineRAG(buscador=buscador, reranker_svc=reranker, config_repo=config_repo)


@pytest.mark.asyncio
async def test_pipeline_ejecuta_fases_end_to_end() -> None:
    """PipelineRAG orquesta clasificar -> buscar -> reranker."""
    f1 = _frag("a")
    f2 = _frag("b")
    pipeline = _make_pipeline(
        candidatos=[(f1, 0.8), (f2, 0.7)],
        rerankeados=[(f1, 0.95), (f2, 0.5)],
    )

    out = await pipeline.ejecutar(
        consulta="Cual es el plazo de apelacion?",
        usuario_id=1,
        expediente_id=None,
    )

    # El output tiene los fragmentos rerankeados en orden.
    assert [frag.qdrant_point_id for frag in out.fragmentos] == ["a", "b"]
    assert list(out.scores) == [0.95, 0.5]
    assert out.query_original == "Cual es el plazo de apelacion?"
    assert out.tipo_respuesta == "consulta_simple"
    assert out.expediente_id is None
    assert out.latencia_ms is not None and out.latencia_ms >= 0


@pytest.mark.asyncio
async def test_pipeline_pasa_consulta_a_buscador() -> None:
    """PipelineRAG pasa la consulta original al HybridSearcher."""
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])

    await pipeline.ejecutar(
        consulta="desobediencia militar",
        usuario_id=1,
        expediente_id=None,
    )

    call = pipeline._buscador.buscar.await_args
    assert call is not None
    assert call.kwargs["query"] == "desobediencia militar"


@pytest.mark.asyncio
async def test_pipeline_pasa_top_k_final_a_reranker() -> None:
    """El top_k_final de ConfiguracionRAG llega al RerankerService."""
    pipeline = _make_pipeline(
        candidatos=[(_frag("a"), 0.0)],
        rerankeados=[(_frag("a"), 0.0)],
    )

    await pipeline.ejecutar(
        consulta="x",
        usuario_id=1,
        expediente_id=None,
    )

    call = pipeline._reranker_svc.aplicar.await_args
    assert call.kwargs["top_k"] == 7  # del config mockeado


@pytest.mark.asyncio
async def test_pipeline_propagates_consulta_sin_expediente() -> None:
    """ConsultaSinExpedienteError del clasificador se propaga al caller."""
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])

    with pytest.raises(ConsultaSinExpedienteError):
        await pipeline.ejecutar(
            consulta="Dictar auto de vista sobre el expediente.",
            usuario_id=1,
            expediente_id=None,  # falta -> raise
        )


@pytest.mark.asyncio
async def test_pipeline_pasa_usuario_id_a_buscador() -> None:
    """Regla 4: usuario_id llega al HybridSearcher."""
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])

    await pipeline.ejecutar(
        consulta="x",
        usuario_id=42,
        expediente_id=None,
    )

    call = pipeline._buscador.buscar.await_args
    assert call.kwargs["usuario_id"] == 42


@pytest.mark.asyncio
async def test_pipeline_expandir_false_resuelve_breadcrumbs_si_hay_expansor() -> None:
    """G6: con expandir=False y expansor configurado, resuelve breadcrumbs.

    El LLM necesita saber la posicion jerarquica del fragmento (Art. X de
    Capitulo Y de Titulo Z) aunque no se expanda el contexto completo.
    """
    from src.domain.value_objects.contexto_expandido import ContextoExpandido

    frag = _frag("pt-1")
    contexto_base = _make_pipeline(
        candidatos=[(frag, 0.9)],
        rerankeados=[(frag, 0.9)],
    )

    # Expansor fake con resolver_breadcrumbs
    expansor = MagicMock()
    expandido = ContextoExpandido(
        fragmentos_con_padres=(frag,),
        scores=(0.9,),
        query_original="x",
        tipo_respuesta="consulta_simple",
        expediente_id=None,
        breadcrumbs=(("CPPM", "CPPM_1", "pt-1"),),
    )
    expansor.resolver_breadcrumbs = AsyncMock(return_value=expandido)

    pipeline = PipelineRAG(
        buscador=contexto_base._buscador,
        reranker_svc=contexto_base._reranker_svc,
        config_repo=contexto_base._config,
        expansor=expansor,  # type: ignore[arg-type]
    )

    resultado = await pipeline.ejecutar(
        consulta="x",
        usuario_id=1,
        expediente_id=None,
        expandir=False,
    )

    expansor.resolver_breadcrumbs.assert_awaited_once()
    assert resultado.breadcrumbs == (("CPPM", "CPPM_1", "pt-1"),)
    # No se llama expandir completo
    expansor.expandir.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_expandir_false_sin_expansor_devuelve_plano() -> None:
    """G6: sin expansor y expandir=False, devuelve ContextoRecuperado plano."""
    pipeline = _make_pipeline(
        candidatos=[(_frag("a"), 0.9)],
        rerankeados=[(_frag("a"), 0.9)],
    )

    resultado = await pipeline.ejecutar(
        consulta="x",
        usuario_id=1,
        expediente_id=None,
        expandir=False,
    )

    assert not hasattr(resultado, "breadcrumbs")  # ContextoRecuperado plano


@pytest.mark.asyncio
async def test_pipeline_marca_solo_expediente_para_tipo_borrador() -> None:
    """Regla 5 / teoria dictamenes-auditor: al generar un borrador (tipo con
    expediente), el filtro para Qdrant es estricto — solo_expediente=True.

    Asi la doctrina global (expediente_id NULL en payload) NO compite con
    los obrados del caso al redactar los ANTECEDENTES del documento.
    """
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])

    await pipeline.ejecutar(
        consulta="Elaborá el dictamen de radicatoria del expediente.",
        usuario_id=1,
        expediente_id=13,
    )

    call = pipeline._buscador.buscar.await_args_list[0]
    assert call is not None
    filtros = call.kwargs["filtros"]
    assert filtros.get("solo_expediente") is True
    assert filtros.get("expediente_id") == "13"


@pytest.mark.asyncio
async def test_pipeline_consulta_simple_sin_solo_expediente() -> None:
    """consulta_simple conserva el OR doctrina (Plan C1.2): el chat libre
    SI se beneficia de recuperar normas globales junto a obrados."""
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])

    await pipeline.ejecutar(
        consulta="Que dice el articulo sobre abandono de servicio?",
        usuario_id=1,
        expediente_id=None,
    )

    call = pipeline._buscador.buscar.await_args
    assert call is not None
    assert "solo_expediente" not in call.kwargs["filtros"]


@pytest.mark.asyncio
async def test_fallback_obrados_se_dispara_sin_seleccion_explicita() -> None:
    """Borrador, expediente, sin obras en candidatos y SIN obra_ids elegidos ->
    el fallback trae obrados de PG para preservar los antecedentes."""
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])
    buscador = MagicMock()  # sin spec: debe exponer _fragmento_repo
    buscador.buscar = AsyncMock(return_value=[(_frag("q1"), 0.5)])
    get_by_exp = AsyncMock(return_value=[])
    buscador._fragmento_repo.get_by_expediente = get_by_exp
    pipeline._buscador = buscador

    await pipeline.ejecutar(
        consulta="Elaborá el auto de vista del expediente.",
        usuario_id=1,
        expediente_id=13,
    )
    get_by_exp.assert_awaited_once()


@pytest.mark.asyncio
async def test_fallback_obrados_respeta_seleccion_de_obras() -> None:
    """Si el usuario eligio obras explicitas (obra_ids), el fallback NO debe
    inyectar otras obras del expediente: se respeta la seleccion."""
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])
    buscador = MagicMock()
    buscador.buscar = AsyncMock(return_value=[(_frag("q1"), 0.5)])
    get_by_exp = AsyncMock(return_value=[])
    buscador._fragmento_repo.get_by_expediente = get_by_exp
    pipeline._buscador = buscador

    await pipeline.ejecutar(
        consulta="Elaborá el auto de vista del expediente.",
        usuario_id=1,
        expediente_id=13,
        obra_ids=[7],
    )
    get_by_exp.assert_not_awaited()


@pytest.mark.asyncio
async def test_borrador_fusiona_normas_del_corpus() -> None:
    """A2: en un borrador con expediente se hace una 2da busqueda sobre el
    corpus de normas (sin expediente) y se fusionan como candidatas al reranker."""
    obr = _frag("q-obras")
    norm = _frag("q-normas")
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])
    buscador = MagicMock()
    # 1ra = obras del caso; 2da = normas del corpus (sin expediente).
    buscador.buscar = AsyncMock(side_effect=[[(obr, 0.5)], [(norm, 0.4)]])
    pipeline._buscador = buscador
    captadas: list[tuple[Fragmento, float]] = []
    pipeline._reranker_svc.aplicar = AsyncMock(
        side_effect=lambda *, query, candidatos, top_k: captadas.extend(candidatos) or []
    )

    await pipeline.ejecutar(
        consulta="Elaborá el auto de vista del expediente.",
        usuario_id=1,
        expediente_id=13,
    )
    assert buscador.buscar.await_count == 2
    segunda_filtros = buscador.buscar.await_args_list[1].kwargs["filtros"]
    assert segunda_filtros.get("tipo_fuente") == "norma"
    # El reranker recibio obrados DEL CASO + normas del corpus fusionados.
    assert {f.qdrant_point_id for f, _ in captadas} == {"q-obras", "q-normas"}


@pytest.mark.asyncio
async def test_consulta_simple_no_dispara_busqueda_corpus_extra() -> None:
    """En consulta_simple ya hay OR(expediente NULL) -> no hace falta la 2da."""
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])
    buscador = MagicMock()
    buscador.buscar = AsyncMock(return_value=[])
    pipeline._buscador = buscador
    await pipeline.ejecutar(
        consulta="Que dice el articulo sobre abandono?",
        usuario_id=1,
        expediente_id=None,
    )
    assert buscador.buscar.await_count == 1


@pytest.mark.asyncio
async def test_pipeline_corpus_refs_directos_sin_obra_ids() -> None:
    """T1: corpus_refs válidos llegan como queries explícitas al buscador."""
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])

    await pipeline.ejecutar(
        consulta="nulidad de oficio",
        usuario_id=1,
        expediente_id=None,
        corpus_refs=["SCP-0623-2024-S4"],
    )

    call = pipeline._buscador.buscar.await_args
    assert call is not None
    extras = call.kwargs["queries_extra"]
    abrs = [f.get("abreviatura") for _q, f in extras]
    assert "SCP-0623-2024-S4" in abrs


@pytest.mark.asyncio
async def test_pipeline_corpus_ref_desconocido_se_ignora() -> None:
    """T1: ref desconocida no rompe (warning, sin queries extra por ella)."""
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])

    await pipeline.ejecutar(
        consulta="nulidad de oficio",
        usuario_id=1,
        expediente_id=None,
        corpus_refs=["NO-EXISTE-XXX"],
    )

    call = pipeline._buscador.buscar.await_args
    assert call is not None
    extras = call.kwargs["queries_extra"]
    abrs = [f.get("abreviatura") for _q, f in extras]
    assert "NO-EXISTE-XXX" not in abrs


@pytest.mark.asyncio
async def test_pipeline_alcance_es_automatico_no_hay_selector() -> None:
    """El alcance ya no lo elige el usuario: con o sin expediente se busca en
    todas las fuentes (normas, jurisprudencia, doctrina y obrados del caso)."""
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])

    await pipeline.ejecutar(consulta="plazo de apelación", usuario_id=1, expediente_id=7)

    call = pipeline._buscador.buscar.await_args_list[0]  # busqueda principal
    assert "tipo_fuente" not in call.kwargs["filtros"]
    assert "alcance" not in call.kwargs


@pytest.mark.asyncio
async def test_pipeline_ya_no_acepta_alcance() -> None:
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])

    with pytest.raises(TypeError):
        await pipeline.ejecutar(
            consulta="x", usuario_id=1, expediente_id=None, alcance="solo-leyes"
        )


@pytest.mark.asyncio
async def test_pipeline_debido_proceso_agrega_consultas_dirigidas() -> None:
    """«debido proceso» debe pedir CPE 115 y CPP 1 (supletorio) de forma explícita."""
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])

    await pipeline.ejecutar(
        consulta="dime sobre el articulo del debido proceso explicalo",
        usuario_id=1,
        expediente_id=None,
    )

    call = pipeline._buscador.buscar.await_args
    assert call is not None
    refs = [
        (f.get("abreviatura"), f.get("numero_articulo")) for _q, f in call.kwargs["queries_extra"]
    ]
    assert ("CPE", 115) in refs
    assert ("CPP", 1) in refs


def _frag_tipo(qid: str, *, norma: bool) -> Fragmento:
    return Fragmento(
        id=None,
        norma_id=1 if norma else None,
        obra_id=None if norma else 5,
        expediente_id=None if norma else 13,
        qdrant_point_id=qid,
        texto="...",
        padre_ref_id=None,
        padre_ref_key=None,
        nivel_jerarquico=4,
        metadatos=None,
        tipo_chunk="articulo_simple" if norma else "obra_ventana",
    )


@pytest.mark.asyncio
async def test_consulta_simple_con_expediente_tambien_suma_las_normas_del_corpus() -> None:
    """El corpus juridico siempre esta: con expediente, la consulta simple lo
    pedia solo a la busqueda principal (restringida al caso) y no traia normas."""
    pipeline = _make_pipeline(candidatos=[], rerankeados=[])
    buscador = MagicMock()
    buscador.buscar = AsyncMock(side_effect=[[(_frag("q-obra"), 0.5)], [(_frag("q-norma"), 0.4)]])
    pipeline._buscador = buscador

    await pipeline.ejecutar(consulta="de que trata el caso", usuario_id=1, expediente_id=13)

    assert buscador.buscar.await_count == 2
    assert buscador.buscar.await_args_list[1].kwargs["filtros"].get("tipo_fuente") == "norma"


@pytest.mark.asyncio
async def test_el_top_reserva_un_minimo_de_normas_del_corpus() -> None:
    """Aunque los obrados del caso ocupen todo el top, entran normas del corpus."""
    obras = [(_frag_tipo(f"o{i}", norma=False), 0.9 - i / 100) for i in range(7)]
    normas = [(_frag_tipo(f"n{i}", norma=True), 0.3) for i in range(3)]
    pipeline = _make_pipeline(candidatos=[], rerankeados=obras[:7])
    pipeline._buscador.buscar = AsyncMock(side_effect=[obras, normas])
    pipeline._reranker_svc.aplicar = AsyncMock(
        side_effect=lambda *, query, candidatos, top_k: candidatos[:top_k]
    )

    ctx = await pipeline.ejecutar(consulta="de que trata el caso", usuario_id=1, expediente_id=13)

    ids = [f.qdrant_point_id for f in ctx.fragmentos]
    assert len(ids) == 7
    assert sum(1 for i in ids if i.startswith("n")) >= 2
    assert ids[0] == "o0"  # el resto conserva su orden
