"""Tests F3.2: punteros N2/N3 (seleccionar corpus + retrieval explícito).

- SeleccionarCorpus crea obra puntero (sin duplicar contenido) solo para
  normas N2/N3 indexadas; leyes e inexistentes fallan claro.
- PipelineRAG resuelve obras puntero a corpus_refs (Regla 5) y las pide
  como queries explícitas por abreviatura, sin umbral.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.doctrina.seleccionar_corpus import (
    CorpusNoSeleccionableError,
    SeleccionarCorpus,
    SeleccionarCorpusRequest,
)


def _norma(abreviatura: str, jerarquia: str, indexado: bool = True):
    return SimpleNamespace(
        id=5,
        nombre=f"Nombre {abreviatura}",
        abreviatura=abreviatura,
        tipo="scp_tcp",
        jerarquia=jerarquia,
        indexado=indexado,
        estado_visibilidad="global",
        propietario_id=None,
    )


def _repos(norma):
    norma_repo = MagicMock()
    norma_repo.get_by_abreviatura = AsyncMock(return_value=norma)
    obra_repo = MagicMock()

    async def _guardar(obra):
        obra.id = 77
        return obra

    obra_repo.guardar = AsyncMock(side_effect=_guardar)
    return obra_repo, norma_repo


@pytest.mark.asyncio
async def test_seleccionar_scp_crea_puntero() -> None:
    """SCP indexada -> obra puntero privada con corpus_ref, sin contenido."""
    obra_repo, norma_repo = _repos(_norma("SCP-0623-2024-S4", "jurisprudencia"))
    uc = SeleccionarCorpus(obra_repo, norma_repo)
    resp = await uc.ejecutar(
        SeleccionarCorpusRequest(abreviatura="SCP-0623-2024-S4", propietario_id=26, expediente_id=8)
    )
    assert resp.obra_id == 77
    assert resp.estado_visibilidad == "privado"
    puntero = obra_repo.guardar.await_args.args[0]
    assert puntero.tipo_documento == "jurisprudencia"
    assert puntero.corpus == "jurisprudencia"
    assert puntero.corpus_ref == "SCP-0623-2024-S4"
    assert puntero.contenido_texto == ""
    assert puntero.expediente_id == 8


@pytest.mark.asyncio
async def test_seleccionar_libro_tipo_doctrina_libro() -> None:
    """Libro N3 -> puntero tipo doctrina_libro."""
    obra_repo, norma_repo = _repos(_norma("LIB-ATIENZA-INTERP-2019", "doctrina"))
    uc = SeleccionarCorpus(obra_repo, norma_repo)
    resp = await uc.ejecutar(
        SeleccionarCorpusRequest(abreviatura="LIB-ATIENZA-INTERP-2019", propietario_id=26)
    )
    assert resp.obra_id == 77
    puntero = obra_repo.guardar.await_args.args[0]
    assert puntero.tipo_documento == "doctrina_libro"
    assert puntero.expediente_id is None


@pytest.mark.asyncio
async def test_seleccionar_una_ley_crea_un_puntero_de_norma() -> None:
    """Las normas tambien se fijan (aunque el corpus juridico siempre esta)."""
    obra_repo, norma_repo = _repos(_norma("CPPM", "militar"))
    uc = SeleccionarCorpus(obra_repo, norma_repo)
    await uc.ejecutar(SeleccionarCorpusRequest(abreviatura="CPPM", propietario_id=26))
    puntero = obra_repo.guardar.await_args.args[0]
    assert puntero.tipo_documento == "norma_corpus"
    assert puntero.corpus == "norma"
    assert puntero.corpus_ref == "CPPM"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "estado,propietario,visible",
    [
        ("global", None, True),
        ("privado", 26, True),  # propia
        ("pendiente", 26, True),  # propia, en revision
        ("privado", 99, False),  # de otro
        ("pendiente", 99, False),
        ("rechazado", 26, False),
    ],
)
async def test_solo_se_selecciona_lo_global_o_propio(estado, propietario, visible) -> None:
    norma = _norma("LIB-X", "doctrina")
    norma.estado_visibilidad = estado
    norma.propietario_id = propietario
    obra_repo, norma_repo = _repos(norma)
    uc = SeleccionarCorpus(obra_repo, norma_repo)

    if visible:
        await uc.ejecutar(SeleccionarCorpusRequest(abreviatura="LIB-X", propietario_id=26))
        obra_repo.guardar.assert_awaited_once()
    else:
        with pytest.raises(CorpusNoSeleccionableError):
            await uc.ejecutar(SeleccionarCorpusRequest(abreviatura="LIB-X", propietario_id=26))
        obra_repo.guardar.assert_not_called()


@pytest.mark.asyncio
async def test_seleccionar_inexistente_y_no_indexada_falla() -> None:
    """Inexistente o sin indexar -> 404 claro, sin guardar."""
    obra_repo, norma_repo = _repos(None)
    uc = SeleccionarCorpus(obra_repo, norma_repo)
    with pytest.raises(CorpusNoSeleccionableError):
        await uc.ejecutar(SeleccionarCorpusRequest(abreviatura="SCP-0000", propietario_id=26))

    obra_repo2, norma_repo2 = _repos(_norma("SCP-0623-2024-S4", "jurisprudencia", False))
    uc2 = SeleccionarCorpus(obra_repo2, norma_repo2)
    with pytest.raises(CorpusNoSeleccionableError):
        await uc2.ejecutar(
            SeleccionarCorpusRequest(abreviatura="SCP-0623-2024-S4", propietario_id=26)
        )


def _frag_doctrina(qid: str, abrev: str):
    from src.domain.entities.fragmento import Fragmento

    return Fragmento(
        id=None,
        norma_id=11,
        obra_id=None,
        expediente_id=None,
        qdrant_point_id=qid,
        texto="doctrina",
        padre_ref_id=None,
        padre_ref_key=f"{abrev}_SEC-GENERAL-3",
        nivel_jerarquico=4,
        metadatos=None,
        tipo_chunk="doctrina_seccion",
    )


def test_cupo_doctrina_recorta_no_explicitos() -> None:
    """Máximo 2 chunks N3 no explícitos; el resto (leyes) intacto."""
    from src.application.services.pipeline_rag import PipelineRAG

    frag_ley = _frag_doctrina("ley-1", "CPPM")
    frag_ley.tipo_chunk = "articulo_simple"
    candidatos = [
        (frag_ley, 0.9),
        (_frag_doctrina("d1", "LIB-A"), 0.8),
        (_frag_doctrina("d2", "LIB-A"), 0.7),
        (_frag_doctrina("d3", "LIB-B"), 0.6),
    ]
    PipelineRAG._aplicar_cupo_doctrina(candidatos, set())
    assert [f.qdrant_point_id for f, _ in candidatos] == ["ley-1", "d1", "d2"]


def test_cupo_doctrina_respeta_explicitos() -> None:
    """Abreviaturas explícitas del vocal no cuentan para el cupo."""
    from src.application.services.pipeline_rag import PipelineRAG

    candidatos = [
        (_frag_doctrina("d1", "LIB-A"), 0.8),
        (_frag_doctrina("d2", "LIB-A"), 0.7),
        (_frag_doctrina("d3", "LIB-B"), 0.6),
    ]
    PipelineRAG._aplicar_cupo_doctrina(candidatos, {"LIB-B"})
    assert [f.qdrant_point_id for f, _ in candidatos] == ["d1", "d2", "d3"]


@pytest.mark.asyncio
async def test_pipeline_toma_recomendadas_si_no_obra_ids() -> None:
    """Sin fijación explícita: recomendadas del expediente entran igual."""
    from src.application.services.pipeline_rag import PipelineRAG

    buscador = MagicMock()
    buscador.buscar = AsyncMock(return_value=[])
    reranker = MagicMock()
    reranker.aplicar = AsyncMock(return_value=[])
    config = MagicMock()
    config.get_config = AsyncMock(
        return_value=MagicMock(
            top_k_denso=5,
            top_k_lexico=5,
            top_k_final=7,
            score_threshold=0.9,
            normalizar_query=False,
        )
    )
    reco_repo = MagicMock()
    reco_repo.listar_por_expediente = AsyncMock(
        return_value=[
            SimpleNamespace(id=1, corpus_ref="SCP-0623-2024-S4", corpus="jurisprudencia"),
            SimpleNamespace(id=2, corpus_ref=None, corpus=None),
        ]
    )
    pipeline = PipelineRAG(
        buscador=buscador,
        reranker_svc=reranker,
        config_repo=config,
        expansor=None,
        event_bus=None,
        recomendacion_repo=reco_repo,
    )
    await pipeline.ejecutar(
        consulta="nulidad de oficio",
        usuario_id=26,
        expediente_id=8,
        expandir=False,
    )
    kwargs = buscador.buscar.await_args_list[0].kwargs  # busqueda principal
    abrs = [f.get("abreviatura") for _q, f in kwargs["queries_extra"]]
    assert "SCP-0623-2024-S4" in abrs
    reco_repo.listar_por_expediente.assert_awaited_once_with(8)


@pytest.mark.asyncio
async def test_pipeline_no_pide_recomendadas_si_hay_explicitos() -> None:
    """Con corpus_refs explícitos no se consulta recomendaciones."""
    from src.application.services.pipeline_rag import PipelineRAG

    buscador = MagicMock()
    buscador.buscar = AsyncMock(return_value=[])
    reranker = MagicMock()
    reranker.aplicar = AsyncMock(return_value=[])
    config = MagicMock()
    config.get_config = AsyncMock(
        return_value=MagicMock(
            top_k_denso=5,
            top_k_lexico=5,
            top_k_final=7,
            score_threshold=0.9,
            normalizar_query=False,
        )
    )
    reco_repo = MagicMock()
    reco_repo.listar_por_expediente = AsyncMock(return_value=[])
    pipeline = PipelineRAG(
        buscador=buscador,
        reranker_svc=reranker,
        config_repo=config,
        expansor=None,
        event_bus=None,
        recomendacion_repo=reco_repo,
    )
    await pipeline.ejecutar(
        consulta="nulidad",
        usuario_id=26,
        expediente_id=8,
        expandir=False,
        corpus_refs=["SCP-0663-2025-S2"],
    )
    reco_repo.listar_por_expediente.assert_not_called()


def _pipeline_con_punteros():
    from src.application.services.pipeline_rag import PipelineRAG

    buscador = MagicMock()
    buscador.buscar = AsyncMock(return_value=[])
    reranker = MagicMock()
    reranker.aplicar = AsyncMock(return_value=[])
    config = MagicMock()
    config.get_config = AsyncMock(
        return_value=MagicMock(
            top_k_denso=5,
            top_k_lexico=5,
            top_k_final=7,
            score_threshold=0.9,
            normalizar_query=False,
        )
    )
    obra_repo = MagicMock()
    obra_repo.obtener_por_ids = AsyncMock(
        return_value={
            10: SimpleNamespace(id=10, expediente_id=8, corpus_ref="SCP-0623-2024-S4"),
            11: SimpleNamespace(id=11, expediente_id=8, corpus_ref=None),
        }
    )
    pipeline = PipelineRAG(
        buscador=buscador,
        reranker_svc=reranker,
        config_repo=config,
        expansor=None,
        event_bus=None,
        obra_repo=obra_repo,
    )
    return pipeline, buscador


@pytest.mark.asyncio
async def test_pipeline_separa_punteros_a_queries_explicitas() -> None:
    """Obra puntero -> query por abreviatura sin umbral; real queda en filtro."""
    pipeline, buscador = _pipeline_con_punteros()
    await pipeline.ejecutar(
        consulta="nulidad de oficio",
        usuario_id=26,
        expediente_id=8,
        expandir=False,
        obra_ids=[10, 11],
    )
    kwargs = buscador.buscar.await_args_list[0].kwargs  # busqueda principal
    # La obra real sigue en el filtro; el puntero sale del filtro.
    assert kwargs["filtros"].get("obra_ids") == [11]
    extras = kwargs["queries_extra"]
    abrs = [f.get("abreviatura") for _q, f in extras]
    assert "SCP-0623-2024-S4" in abrs


@pytest.mark.asyncio
async def test_pipeline_sin_obra_repo_ignora_punteros() -> None:
    """Sin obra_repo (compat): obra_ids pasan intactos, sin queries extra."""
    from src.application.services.pipeline_rag import PipelineRAG

    buscador = MagicMock()
    buscador.buscar = AsyncMock(return_value=[])
    reranker = MagicMock()
    reranker.aplicar = AsyncMock(return_value=[])
    config = MagicMock()
    config.get_config = AsyncMock(
        return_value=MagicMock(
            top_k_denso=5,
            top_k_lexico=5,
            top_k_final=7,
            score_threshold=0.9,
            normalizar_query=False,
        )
    )
    pipeline = PipelineRAG(
        buscador=buscador,
        reranker_svc=reranker,
        config_repo=config,
        expansor=None,
        event_bus=None,
    )
    await pipeline.ejecutar(
        consulta="nulidad",
        usuario_id=26,
        expediente_id=8,
        expandir=False,
        obra_ids=[10],
    )
    kwargs = buscador.buscar.await_args_list[0].kwargs  # busqueda principal
    assert kwargs["filtros"].get("obra_ids") == [10]
