"""Sincroniza el payload `visibilidad` de los puntos de una obra (F-12)."""

from __future__ import annotations

from unittest.mock import MagicMock

from qdrant_client.http import models

from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo


async def test_actualizar_visibilidad_obra_hace_set_payload_por_obra_id() -> None:
    repo = QdrantCorpusRepo.__new__(QdrantCorpusRepo)  # sin conexion
    repo._client = MagicMock()

    await repo.actualizar_visibilidad_obra(7, "publicado")

    kwargs = repo._client.set_payload.call_args.kwargs
    assert kwargs["collection_name"] == QdrantCorpusRepo.COLLECTION_NAME
    assert kwargs["payload"] == {"visibilidad": "publicado"}
    condicion = kwargs["points"].must[0]
    assert isinstance(condicion, models.FieldCondition)
    assert condicion.key == "obra_id"
    assert condicion.match.value == 7


async def test_actualizar_payload_obra_hace_set_payload_por_obra_id() -> None:
    repo = QdrantCorpusRepo.__new__(QdrantCorpusRepo)
    repo._client = MagicMock()

    await repo.actualizar_payload_obra(7, {"tipo_fuente": "jurisprudencia"})

    kwargs = repo._client.set_payload.call_args.kwargs
    assert kwargs["payload"] == {"tipo_fuente": "jurisprudencia"}
    assert kwargs["points"].must[0].match.value == 7


async def test_actualizar_payload_norma_hace_set_payload_por_norma_id() -> None:
    repo = QdrantCorpusRepo.__new__(QdrantCorpusRepo)
    repo._client = MagicMock()

    await repo.actualizar_payload_norma(3, {"visibilidad": "global"})

    kwargs = repo._client.set_payload.call_args.kwargs
    assert kwargs["payload"] == {"visibilidad": "global"}
    condicion = kwargs["points"].must[0]
    assert (condicion.key, condicion.match.value) == ("norma_id", 3)
