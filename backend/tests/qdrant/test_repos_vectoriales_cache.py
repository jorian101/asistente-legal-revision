"""Los repos Qdrant son singletons de proceso, no uno por request (F-23).

Cada `QdrantCorpusRepo()` construye un `QdrantClient`, y su constructor hace un
chequeo de version por HTTP; crearlo en cada request sumaba esa latencia y un
cliente sin cerrar por peticion.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.adapters.http import dependencies as deps

FACTORIAS = (
    deps.get_vector_repo,
    deps.get_vector_repo_jurisprudencia,
    deps.get_vector_repo_doctrina,
)


@pytest.fixture(autouse=True)
def _cache_limpia():
    deps.cerrar_repos_vectoriales()
    yield
    deps.cerrar_repos_vectoriales()


@pytest.mark.parametrize("factoria", FACTORIAS)
def test_la_factoria_devuelve_siempre_la_misma_instancia(factoria) -> None:
    with patch("src.adapters.qdrant.qdrant_corpus_repo.QdrantClient") as cliente:
        primero = factoria()
        segundo = factoria()

    assert primero is segundo
    assert cliente.call_count == 1  # un solo QdrantClient, no uno por llamada


def test_cerrar_repos_cierra_el_cliente_y_reinicia_la_cache() -> None:
    with patch("src.adapters.qdrant.qdrant_corpus_repo.QdrantClient") as cliente:
        instancia_cliente = MagicMock()
        cliente.return_value = instancia_cliente
        repo = deps.get_vector_repo()

        deps.cerrar_repos_vectoriales()

        instancia_cliente.close.assert_called_once()
        assert deps.get_vector_repo() is not repo  # cache reiniciada: nueva instancia
