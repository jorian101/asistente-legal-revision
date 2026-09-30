"""add_sparse_text_vector.py con una coleccion vacia (recien creada sin sparse).

Abortaba con codigo 2 ("coleccion vacia o scroll fallo"): un despliegue nuevo no tenia
como agregar el sparse. Sin puntos no hay nada que volcar: basta recrearla, sin perdida
de datos, con el esquema completo del adapter.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from qdrant_migrations import add_sparse_text_vector as migracion

MODULO = "qdrant_migrations.add_sparse_text_vector"


def _repo(puntos: int) -> MagicMock:
    repo = MagicMock()
    repo.COLLECTION_NAME = "corpus_juridico"
    repo.SPARSE_VECTOR_NAME = "text-sparse"
    info = SimpleNamespace(
        points_count=puntos,
        config=SimpleNamespace(
            params=SimpleNamespace(vectors=SimpleNamespace(size=768), sparse_vectors=None)
        ),
    )
    repo._client.get_collection.return_value = info
    repo._client.scroll.return_value = ([], None)
    return repo


async def _main(repo: MagicMock, argv: list[str]) -> int:
    with (
        patch(f"{MODULO}.QdrantCorpusRepo", return_value=repo),
        patch(f"{MODULO}.get_settings", return_value=SimpleNamespace(embedding_dim=768)),
        patch.object(sys, "argv", ["add_sparse_text_vector.py", *argv]),
    ):
        return await migracion.main()


@pytest.mark.asyncio
async def test_coleccion_vacia_con_yes_se_recrea_con_el_esquema_completo() -> None:
    repo = _repo(puntos=0)

    codigo = await _main(repo, ["--yes"])

    assert codigo == 0
    repo._client.delete_collection.assert_called_once_with("corpus_juridico")
    repo.crear_coleccion.assert_called_once()


@pytest.mark.asyncio
async def test_coleccion_vacia_sin_yes_no_toca_nada() -> None:
    repo = _repo(puntos=0)

    codigo = await _main(repo, [])

    assert codigo == 0
    repo._client.delete_collection.assert_not_called()
    repo.crear_coleccion.assert_not_called()
