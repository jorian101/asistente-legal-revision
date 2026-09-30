"""Una coleccion Qdrant inexistente (jurisprudencia/doctrina aun sin ingerir) no es un error.

HybridSearcher hace fan-out a `jurisprudencia` y `doctrina`; en un despliegue nuevo, o con
solo normas indexadas, esas colecciones no existen y Qdrant responde 404: cada consulta RAG
fallaba entera. Debe contar como "sin resultados". Verificado contra Qdrant real.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import SparseVector

from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo


def _repo(client: MagicMock) -> QdrantCorpusRepo:
    with patch("src.adapters.qdrant.qdrant_corpus_repo.QdrantClient", return_value=client):
        return QdrantCorpusRepo(url="http://x:6333", embedding_dim=4)


def _404() -> UnexpectedResponse:
    return UnexpectedResponse(
        status_code=404,
        reason_phrase="Not Found",
        content=b'{"status":{"error":"Not found: Collection `jurisprudencia` doesn\'t exist!"}}',
        headers=None,
    )


def _cliente_sin_coleccion() -> MagicMock:
    client = MagicMock()
    client.get_collection.side_effect = _404()
    client.query_points.side_effect = _404()
    return client


@pytest.mark.asyncio
async def test_search_hybrid_de_una_coleccion_inexistente_devuelve_vacio() -> None:
    repo = _repo(_cliente_sin_coleccion())

    resultado = await repo.search_hybrid(
        dense_vector=[0.1] * 4,
        sparse_vector=SparseVector(indices=[1], values=[1.0]),
        alpha=0.5,
        filters={"usuario_id": 3},
        limit=10,
    )

    assert resultado == []


@pytest.mark.asyncio
async def test_search_dense_de_una_coleccion_inexistente_devuelve_vacio() -> None:
    repo = _repo(_cliente_sin_coleccion())

    assert await repo.search_dense([0.1] * 4, {"usuario_id": 3}, 10) == []


@pytest.mark.asyncio
async def test_otros_errores_de_qdrant_siguen_propagandose() -> None:
    client = _cliente_sin_coleccion()
    client.query_points.side_effect = UnexpectedResponse(
        status_code=500, reason_phrase="Error", content=b"boom", headers=None
    )
    repo = _repo(client)

    with pytest.raises(UnexpectedResponse):
        await repo.search_dense([0.1] * 4, {"usuario_id": 3}, 10)


def test_una_coleccion_inexistente_no_cachea_la_ausencia_de_sparse() -> None:
    """Si la coleccion se crea despues (con sparse), no debe requerir reiniciar el proceso."""
    repo = _repo(_cliente_sin_coleccion())

    assert repo._collection_has_sparse() is False
    assert repo._sparse_checked is False
