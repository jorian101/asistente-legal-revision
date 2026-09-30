"""Tests F3.1: libros académicos como N3 (colección `doctrina` separada).

- SegmentadorLibro: maestro no indexable + ventanas con página y sección.
- IndexarNorma rutea LIB-* al repo doctrina con payload N3
  (tipo_fuente, autor, obra, pagina, nivel_autoridad=orientativa).
- QdrantDoctrinaRepo: colección propia + índices N3.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.corpus.indexar_norma import (
    IndexarNorma,
    IndexarNormaRequest,
    tipo_jerarquia_para,
)
from src.domain.services.segmentacion.base import (
    ArbolJerarquico,
    FragmentoProducible,
)

LIBRO_MUESTRA = """https://lh3.googleusercontent.com/notebooklm/abc=w800

aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee

TÍTULO DEL LIBRO
Autor Ejemplo

https://lh3.googleusercontent.com/notebooklm/def=w800

bbbbbbbb-cccc-dddd-eeee-ffffffffffff

CONTENIDO
Capítulo primero ... 1
Capítulo segundo ... 20

https://lh3.googleusercontent.com/notebooklm/jkl=w800

cccccccc-dddd-eeee-ffff-000000000000

CAPÍTULO PRIMERO
Texto del primer capítulo con contenido jurídico suficiente para
partir en ventanas razonables y verificar la segmentación.

https://lh3.googleusercontent.com/notebooklm/ghi=w800

cccccccc-dddd-eeee-ffff-000000000000

CAPÍTULO SEGUNDO
Segundo capítulo con más contenido para la segunda ventana de texto.
"""


def test_libro_maestro_pagina_y_seccion() -> None:
    """Maestro con ficha + fragmentos con autor/obra/página/sección."""
    import src.domain.services.segmentacion as _s  # noqa: F401 (auto-registro)
    from src.domain.services.segmentacion.registro import SegmentadorRegistry

    seg = SegmentadorRegistry.obtener("LIB-ATIENZA-INTERP-2019")
    arbol = seg.segmentar(LIBRO_MUESTRA)
    maestros = [n for k, n in arbol.nodos.items() if "MASTER" in k]
    assert len(maestros) == 1
    assert maestros[0].metadatos.get("no_indexable") is True
    assert maestros[0].metadatos.get("autor") == "Manuel Atienza Rodríguez"
    assert arbol.fragmentos, "el cuerpo debe producir fragmentos"
    primero = arbol.fragmentos[0]
    assert primero.tipo_chunk == "doctrina_seccion"
    assert primero.metadatos["obra"] == "Interpretación constitucional"
    assert isinstance(primero.metadatos["pagina"], int)
    assert primero.metadatos["pagina"] >= 1
    assert "LIB-ATIENZA-INTERP-2019" in (primero.padre_ref_key or "")


def test_libro_sin_cuerpo_falla_claro() -> None:
    """Libro solo con imágenes (sin texto) no se indexa en silencio."""
    import src.domain.services.segmentacion as _s  # noqa: F401 (auto-registro)
    from src.domain.services.segmentacion.registro import SegmentadorRegistry

    seg = SegmentadorRegistry.obtener("LIB-GUIA-CASO-DELITO")
    with pytest.raises(ValueError, match="Sin cuerpo indexable"):
        seg.segmentar("https://lh3.googleusercontent.com/x=w800\n\nabc-def\n")


def test_tipo_jerarquia_lib() -> None:
    """LIB-* resuelve (doctrina_libro, doctrina)."""
    assert tipo_jerarquia_para("LIB-ATIENZA-INTERP-2019") == (
        "doctrina_libro",
        "doctrina",
    )


def _repos():
    extractor = MagicMock()
    extractor.extract = AsyncMock(side_effect=AssertionError("no debe extraer"))
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1] * 4])
    vector_repo = MagicMock()
    vector_repo._collection_has_sparse = MagicMock(return_value=False)
    vector_repo.upsert_corpus = AsyncMock()
    vector_repo_doctrina = MagicMock()
    vector_repo_doctrina._collection_has_sparse = MagicMock(return_value=False)
    vector_repo_doctrina.upsert_corpus = AsyncMock()
    norma_repo = MagicMock()

    async def _save(norma):
        norma.id = 11
        return norma

    norma_repo.save = AsyncMock(side_effect=_save)
    norma_repo.marcar_indexada = AsyncMock()
    fragmento_repo = MagicMock()
    fragmento_repo.save_many = AsyncMock(side_effect=lambda frags: frags)
    return (
        extractor,
        embedder,
        vector_repo,
        vector_repo_doctrina,
        norma_repo,
        fragmento_repo,
    )


@pytest.mark.asyncio
async def test_indexar_libro_usa_coleccion_doctrina_y_payload_n3() -> None:
    """LIB-* -> repo doctrina, payload N3, colección en respuesta."""
    from src.domain.services.segmentacion import registro

    ext, emb, vec, vec_doc, nrepo, frepo = _repos()
    segmentador = MagicMock()
    segmentador.LIMPIEZA_PROPIA = False
    segmentador.segmentar = MagicMock(
        return_value=ArbolJerarquico(
            abreviatura="LIB-ATIENZA-INTERP-2019",
            raices=[],
            nodos={},
            fragmentos=[
                FragmentoProducible(
                    texto="La interpretación exige ponderar.",
                    nivel_jerarquico=4,
                    tipo_chunk="doctrina_seccion",
                    padre_ref_key="LIB-ATIENZA-INTERP-2019_SEC-GENERAL-3",
                    metadatos={
                        "bloque": "doctrina",
                        "autor": "Manuel Atienza Rodríguez",
                        "obra": "Interpretación constitucional",
                        "pagina": 3,
                        "seccion": "GENERAL",
                    },
                ),
            ],
        )
    )
    orig = registro.SegmentadorRegistry.obtener
    registro.SegmentadorRegistry.obtener = classmethod(lambda cls, abrev: segmentador)
    try:
        uc = IndexarNorma(
            text_extractor=ext,
            embedder=emb,
            vector_repo=vec,
            norma_repo=nrepo,
            fragmento_repo=frepo,
            vector_repo_doctrina=vec_doc,
        )
        result = await uc.ejecutar(
            IndexarNormaRequest(
                abreviatura="LIB-ATIENZA-INTERP-2019",
                ruta_pdf="/tmp/x.txt",
                texto_directo="cuerpo",
            )
        )
    finally:
        registro.SegmentadorRegistry.obtener = orig

    vec.upsert_corpus.assert_not_called()
    vec_doc.upsert_corpus.assert_awaited_once()
    payload = vec_doc.upsert_corpus.await_args.args[0][0]["payload"]
    assert payload["tipo_fuente"] == "doctrina"
    assert payload["autor"] == "Manuel Atienza Rodríguez"
    assert payload["obra"] == "Interpretación constitucional"
    assert payload["pagina"] == 3
    assert payload["nivel_autoridad"] == "orientativa"
    assert result.qdrant_collection == "doctrina"
    norma_guardada = nrepo.save.await_args.args[0]
    assert norma_guardada.tipo == "doctrina_libro"
    assert norma_guardada.jerarquia == "doctrina"


def test_repo_doctrina_coleccion_e_indices() -> None:
    """Subclase: colección propia + índices N3 (sin tocar la base)."""
    from src.adapters.qdrant.qdrant_doctrina_repo import QdrantDoctrinaRepo

    assert QdrantDoctrinaRepo.COLLECTION_NAME == "doctrina"
    repo = QdrantDoctrinaRepo.__new__(QdrantDoctrinaRepo)
    repo._client = MagicMock()
    orig_base = QdrantDoctrinaRepo.__bases__[0]._create_payload_indexes
    llamadas: list[str] = []
    QdrantDoctrinaRepo.__bases__[0]._create_payload_indexes = lambda self: llamadas.append("base")
    try:
        repo._create_payload_indexes()
    finally:
        QdrantDoctrinaRepo.__bases__[0]._create_payload_indexes = orig_base
    assert llamadas == ["base"]
    campos = [c.kwargs["field_name"] for c in repo._client.create_payload_index.call_args_list]
    for esperado in ("autor", "obra", "bloque", "nivel_autoridad"):
        assert esperado in campos
