"""Tests unitarios de los casos de uso de corpus (ListarNormas, VerEstadoIndexacion).

TDD: mockea los ports (NormaRepo, FragmentoRepo) — sin DB real. Verifica
comportamiento del interactor, no detalles de implementación.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.corpus.listar_normas import ListarNormas, NormaResumenDTO
from src.application.corpus.ver_estado_indexacion import (
    EstadoIndexacionDTO,
    VerEstadoIndexacion,
)


def _norma_mock(
    norma_id: int = 1,
    abreviatura: str = "CPPM",
    nombre: str = "CODIGO DE PROCEDIMIENTO PENAL MILITAR",
    tipo: str = "codigo_militar",
    jerarquia: str = "militar",
    version: str | None = None,
    indexado: bool = True,
    indexado_por: int | None = 5,
):
    m = MagicMock()
    m.id = norma_id
    m.abreviatura = abreviatura
    m.nombre = nombre
    m.tipo = tipo
    m.jerarquia = jerarquia
    m.version = version
    m.indexado = indexado
    m.indexado_por = indexado_por
    return m


@pytest.mark.asyncio
async def test_listar_normas_devuelve_resumenes_ordenados():
    norma_repo = MagicMock()
    norma_repo.list_all = AsyncMock(return_value=[_norma_mock(1, "CPE"), _norma_mock(2, "CPPM")])
    uc = ListarNormas(norma_repo)

    result = await uc.ejecutar()

    assert len(result) == 2
    assert all(isinstance(r, NormaResumenDTO) for r in result)
    assert result[0].abreviatura == "CPE"
    assert result[1].abreviatura == "CPPM"
    assert result[0].indexado is True
    assert result[0].indexado_por == 5


@pytest.mark.asyncio
async def test_listar_normas_ordena_por_nombre():
    norma_repo = MagicMock()
    norma_repo.list_all = AsyncMock(
        return_value=[
            _norma_mock(1, "CPPM", nombre="ZZZ CODIGO"),
            _norma_mock(2, "CPE", nombre="AAA CONSTITUCION"),
        ]
    )
    uc = ListarNormas(norma_repo)

    result = await uc.ejecutar(orden="nombre")

    assert [r.abreviatura for r in result] == ["CPE", "CPPM"]


@pytest.mark.asyncio
async def test_listar_normas_orden_invalido():
    norma_repo = MagicMock()
    norma_repo.list_all = AsyncMock(return_value=[])
    uc = ListarNormas(norma_repo)

    with pytest.raises(ValueError):
        await uc.ejecutar(orden="inexistente")


@pytest.mark.asyncio
async def test_listar_normas_vacia():
    norma_repo = MagicMock()
    norma_repo.list_all = AsyncMock(return_value=[])
    uc = ListarNormas(norma_repo)

    result = await uc.ejecutar()

    assert result == []


@pytest.mark.asyncio
async def test_ver_estado_indexacion_norma_existente():
    norma_repo = MagicMock()
    norma_repo.get_by_id = AsyncMock(
        return_value=_norma_mock(7, "LOJM", indexado=False, indexado_por=None)
    )
    fragmento_repo = MagicMock()
    fragmento_repo.count_by_norma = AsyncMock(return_value=42)
    uc = VerEstadoIndexacion(norma_repo, fragmento_repo)

    result = await uc.ejecutar(norma_id=7)

    assert isinstance(result, EstadoIndexacionDTO)
    assert result.norma_id == 7
    assert result.abreviatura == "LOJM"
    assert result.indexado is False
    assert result.indexado_por is None
    assert result.fragmentos_count == 42


@pytest.mark.asyncio
async def test_ver_estado_indexacion_norma_inexistente():
    norma_repo = MagicMock()
    norma_repo.get_by_id = AsyncMock(return_value=None)
    fragmento_repo = MagicMock()
    fragmento_repo.count_by_norma = AsyncMock(return_value=0)
    uc = VerEstadoIndexacion(norma_repo, fragmento_repo)

    result = await uc.ejecutar(norma_id=999)

    assert result is None


@pytest.mark.asyncio
async def test_indexar_norma_happy_path_con_tipo_fuente_y_sparse():
    """D-S2C-02: el UC escribe tipo_fuente=norma y sparse por punto."""
    from src.application.corpus.indexar_norma import (
        IndexarNorma,
        IndexarNormaRequest,
    )
    from src.application.ports.text_extractor import ExtractionResult
    from src.domain.services.segmentacion.base import (
        ArbolJerarquico,
        FragmentoProducible,
    )

    extractor = MagicMock()
    extractor.extract = AsyncMock(
        return_value=ExtractionResult(
            full_text="(1) primero\n\n(2) segundo",
            blocks=[],
            pages_count=1,
            extracted_pages=[1],
            metadata={},
        )
    )
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1] * 4, [0.2] * 4])
    vector_repo = MagicMock()
    vector_repo._collection_has_sparse = MagicMock(return_value=True)
    vector_repo.upsert_corpus = AsyncMock()
    norma_repo = MagicMock()

    async def _save(norma):
        norma.id = 7
        return norma

    norma_repo.save = AsyncMock(side_effect=_save)
    norma_repo.marcar_indexada = AsyncMock()
    fragmento_repo = MagicMock()
    fragmento_repo.save_many = AsyncMock(side_effect=lambda frags: frags)

    segmentador = MagicMock()
    segmentador.segmentar = MagicMock(
        return_value=ArbolJerarquico(
            abreviatura="CPPM",
            raices=[],
            nodos={},
            fragmentos=[
                FragmentoProducible(
                    texto="(1) primero",
                    nivel_jerarquico=4,
                    tipo_chunk="articulo_simple_numeral",
                    padre_ref_key="CPPM_1_MASTER_1",
                    metadatos={"numero_articulo": 1},
                ),
                FragmentoProducible(
                    texto="(2) segundo",
                    nivel_jerarquico=4,
                    tipo_chunk="articulo_simple_numeral",
                    padre_ref_key="CPPM_1_MASTER_2",
                    metadatos={"numero_articulo": 1},
                ),
            ],
        )
    )

    from src.domain.services.segmentacion import registro

    orig = registro.SegmentadorRegistry.obtener
    registro.SegmentadorRegistry.obtener = classmethod(lambda cls, abrev: segmentador)
    try:
        uc = IndexarNorma(
            text_extractor=extractor,
            embedder=embedder,
            vector_repo=vector_repo,
            norma_repo=norma_repo,
            fragmento_repo=fragmento_repo,
        )
        result = await uc.ejecutar(IndexarNormaRequest(abreviatura="CPPM", ruta_pdf="/tmp/x.pdf"))
    finally:
        registro.SegmentadorRegistry.obtener = orig

    assert result.fragmentos_creados == 2
    assert result.vectores_indexados == 2
    puntos = vector_repo.upsert_corpus.await_args.args[0]
    assert len(puntos) == 2
    for p in puntos:
        assert p["payload"]["tipo_fuente"] == "norma"
        assert p["vector_sparse"] is not None
        assert len(p["vector_sparse"]["indices"]) > 0
    norma_repo.marcar_indexada.assert_awaited_once()


@pytest.mark.asyncio
async def test_indexar_persiste_estructurales_sin_vectorizar():
    """D-S2C-06 split: nodos estructurales van a PG (no indexables)."""
    from src.application.corpus.indexar_norma import (
        IndexarNorma,
        IndexarNormaRequest,
    )
    from src.application.ports.text_extractor import ExtractionResult
    from src.domain.services.segmentacion.base import (
        ArbolJerarquico,
        FragmentoProducible,
        NodoJerarquico,
    )

    extractor = MagicMock()
    extractor.extract = AsyncMock(
        return_value=ExtractionResult(
            full_text="texto",
            blocks=[],
            pages_count=1,
            extracted_pages=[1],
            metadata={},
        )
    )
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1] * 4])
    vector_repo = MagicMock()
    vector_repo._collection_has_sparse = MagicMock(return_value=False)
    vector_repo.upsert_corpus = AsyncMock()
    norma_repo = MagicMock()

    async def _save(norma):
        norma.id = 9
        return norma

    norma_repo.save = AsyncMock(side_effect=_save)
    norma_repo.marcar_indexada = AsyncMock()
    fragmento_repo = MagicMock()
    fragmento_repo.save_many = AsyncMock(side_effect=lambda frags: frags)

    segmentador = MagicMock()
    segmentador.__class__.__name__ = "SegmentadorCPM"
    segmentador.segmentar = MagicMock(
        return_value=ArbolJerarquico(
            abreviatura="CPM",
            raices=["CPM_LIBRO_I"],
            nodos={
                "CPM_LIBRO_I": NodoJerarquico(
                    clave="CPM_LIBRO_I",
                    nivel=1,
                    titulo="LIBRO I",
                    hijos=[],
                    metadatos={"tipo_estructura": "LIBRO"},
                ),
            },
            fragmentos=[
                FragmentoProducible(
                    texto="cuerpo",
                    nivel_jerarquico=4,
                    tipo_chunk="articulo_simple",
                    padre_ref_key="CPM_1_MASTER",
                    metadatos={"numero_articulo": 1},
                ),
            ],
        )
    )

    from src.domain.services.segmentacion import registro

    orig = registro.SegmentadorRegistry.obtener
    registro.SegmentadorRegistry.obtener = classmethod(lambda cls, abrev: segmentador)
    try:
        uc = IndexarNorma(
            text_extractor=extractor,
            embedder=embedder,
            vector_repo=vector_repo,
            norma_repo=norma_repo,
            fragmento_repo=fragmento_repo,
        )
        result = await uc.ejecutar(IndexarNormaRequest(abreviatura="CPM", ruta_pdf="/tmp/x.pdf"))
    finally:
        registro.SegmentadorRegistry.obtener = orig

    guardados = fragmento_repo.save_many.await_args.args[0]
    assert len(guardados) == 2  # 1 estructural + 1 indexable
    estructural = guardados[0]
    assert estructural.qdrant_point_id == ""
    assert not estructural.es_indexable
    assert estructural.tipo_chunk == "estructura_libro"
    assert result.fragmentos_creados == 1  # solo indexables
    puntos = vector_repo.upsert_corpus.await_args.args[0]
    assert len(puntos) == 1  # el estructural no va a Qdrant


@pytest.mark.asyncio
async def test_indexar_enlaza_padres_numerales_y_estructura():
    """D-S5K-01: tras save_many se enlaza padre_ref_id (numeral->maestro,
    titulo->libro). El maestro no enlaza a estructura (nivel 2, follow-up)."""
    from src.application.corpus.indexar_norma import (
        IndexarNorma,
        IndexarNormaRequest,
    )
    from src.application.ports.text_extractor import ExtractionResult
    from src.domain.services.segmentacion.base import (
        ArbolJerarquico,
        FragmentoProducible,
        NodoJerarquico,
    )

    extractor = MagicMock()
    extractor.extract = AsyncMock(
        return_value=ExtractionResult(
            full_text="t", blocks=[], pages_count=1, extracted_pages=[1], metadata={}
        )
    )
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1], [0.2], [0.3]])
    vector_repo = MagicMock()
    vector_repo._collection_has_sparse = MagicMock(return_value=False)
    vector_repo.upsert_corpus = AsyncMock()
    norma_repo = MagicMock()

    async def _save(norma):
        norma.id = 5
        return norma

    norma_repo.save = AsyncMock(side_effect=_save)
    norma_repo.marcar_indexada = AsyncMock()
    fragmento_repo = MagicMock()

    _next_id = [100]

    def _save_many(frags):
        for fr in frags:
            _next_id[0] += 1
            fr.id = _next_id[0]
        return frags

    fragmento_repo.save_many = AsyncMock(side_effect=_save_many)
    fragmento_repo.asignar_padres_por_ids = AsyncMock()

    segmentador = MagicMock()
    segmentador.__class__.__name__ = "SegmentadorCPM"
    segmentador.segmentar = MagicMock(
        return_value=ArbolJerarquico(
            abreviatura="CPM",
            raices=["CPM_LIBRO_I"],
            nodos={
                "CPM_LIBRO_I": NodoJerarquico(
                    clave="CPM_LIBRO_I",
                    nivel=1,
                    titulo="LIBRO I",
                    hijos=["CPM_TITULO_II"],
                    metadatos={"tipo_estructura": "LIBRO"},
                ),
                "CPM_TITULO_II": NodoJerarquico(
                    clave="CPM_TITULO_II",
                    nivel=2,
                    titulo="TÍTULO II",
                    hijos=[],
                    metadatos={"tipo_estructura": "TITULO"},
                ),
            },
            fragmentos=[
                FragmentoProducible(
                    texto="sancion comun",
                    nivel_jerarquico=4,
                    tipo_chunk="articulo_simple",
                    padre_ref_key="CPM_9_MASTER",
                    metadatos={"numero_articulo": 9},
                ),
                FragmentoProducible(
                    texto="(1) a",
                    nivel_jerarquico=4,
                    tipo_chunk="articulo_simple_numeral",
                    padre_ref_key="CPM_9_MASTER_1",
                    metadatos={"numero_articulo": 9, "numeral": "1"},
                ),
                FragmentoProducible(
                    texto="(2) b",
                    nivel_jerarquico=4,
                    tipo_chunk="articulo_simple_numeral",
                    padre_ref_key="CPM_9_MASTER_2",
                    metadatos={"numero_articulo": 9, "numeral": "2"},
                ),
            ],
        )
    )

    from src.domain.services.segmentacion import registro

    orig = registro.SegmentadorRegistry.obtener
    registro.SegmentadorRegistry.obtener = classmethod(lambda cls, abrev: segmentador)
    try:
        uc = IndexarNorma(
            text_extractor=extractor,
            embedder=embedder,
            vector_repo=vector_repo,
            norma_repo=norma_repo,
            fragmento_repo=fragmento_repo,
        )
        await uc.ejecutar(IndexarNormaRequest(abreviatura="CPM", ruta_pdf="/tmp/x.pdf"))
    finally:
        registro.SegmentadorRegistry.obtener = orig

    pares = fragmento_repo.asignar_padres_por_ids.await_args.args[0]
    por_id = dict(pares)
    assert len(pares) == 3
    maestro_id = next(
        f.id
        for f in fragmento_repo.save_many.await_args.args[0]
        if f.padre_ref_key == "CPM_9_MASTER" and f.qdrant_point_id
    )
    assert por_id[maestro_id + 1] == maestro_id
    assert por_id[maestro_id + 2] == maestro_id
    libro = next(
        f.id
        for f in fragmento_repo.save_many.await_args.args[0]
        if f.metadatos and f.metadatos.get("clave_estructural") == "CPM_LIBRO_I"
    )
    titulo = next(
        f.id
        for f in fragmento_repo.save_many.await_args.args[0]
        if f.metadatos and f.metadatos.get("clave_estructural") == "CPM_TITULO_II"
    )
    assert por_id[titulo] == libro
    assert maestro_id not in por_id  # nivel 2 es follow-up
