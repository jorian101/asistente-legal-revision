"""Tests del flag SAFETY_ALLOW_COLLECTION_RECREATE en QdrantCorpusRepo.

Cubren 3 invariantes contractuales:
- Sin flag (default=false): un mismatch de dimension bloquea el recreate
  destructivo con RuntimeError claro (no se llama delete_collection).
- Con flag (true): se permite recreate (delete + create) y se loguea warning.
- Misma dimension: no-op (ni warning ni delete).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo
from src.config import Settings


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    """Resetea el lru_cache de Settings para que cada test vea su propio env."""
    Settings.cache_clear()


def _make_collection_info(dim: int) -> MagicMock:
    """Mock del return de get_collection()."""
    info = MagicMock()
    info.config.params.vectors.size = dim
    info.config.params.sparse_vectors = None  # sin sparse por defecto
    return info


def _make_qdrant_client(current_dim: int | None, collection_exists: bool) -> MagicMock:
    """Mock del qdrant-client con collections / get_collection / delete / create."""
    client = MagicMock()
    collections_mock = MagicMock()
    if collection_exists:
        collection_name_obj = MagicMock()
        collection_name_obj.name = QdrantCorpusRepo.COLLECTION_NAME
        collections_mock.collections = [collection_name_obj]
    else:
        collections_mock.collections = []
    client.get_collections.return_value = collections_mock
    if current_dim is not None:
        client.get_collection.return_value = _make_collection_info(current_dim)
    client.delete_collection = MagicMock()
    client.create_collection = MagicMock()
    return client


def _make_repo(client: MagicMock, target_dim: int = 768) -> QdrantCorpusRepo:
    """Crea un repo con cliente inyectado (no necesita conexion real)."""
    # Bypassing el QdrantClient real: usamos object.__new__ para saltar __init__.
    # Luego asignamos los attr internos que necesita _ensure_collection_sync.
    repo = object.__new__(QdrantCorpusRepo)
    repo._client = client
    repo._dim = target_dim
    repo._url = "http://test"
    repo._api_key = None
    return repo


def test_ensure_collection_blocks_recreate_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin SAFETY_ALLOW_COLLECTION_RECREATE (default) -> RuntimeError + no delete."""
    monkeypatch.setenv("SAFETY_ALLOW_COLLECTION_RECREATE", "false")
    client = _make_qdrant_client(current_dim=512, collection_exists=True)
    repo = _make_repo(client, target_dim=768)

    with pytest.raises(RuntimeError) as exc_info:
        repo._ensure_collection_sync()

    # El mensaje debe dar pista accionable.
    msg = str(exc_info.value).lower()
    assert "512" in str(exc_info.value)
    assert "768" in str(exc_info.value)
    assert "safety_allow_collection_recreate" in msg or "safety" in msg.lower()

    client.delete_collection.assert_not_called()
    client.create_collection.assert_not_called()


def test_ensure_collection_recreates_when_flag_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con SAFETY_ALLOW_COLLECTION_RECREATE=1 -> delete + create llamado."""
    monkeypatch.setenv("SAFETY_ALLOW_COLLECTION_RECREATE", "true")
    client = _make_qdrant_client(current_dim=512, collection_exists=True)
    repo = _make_repo(client, target_dim=768)

    repo._ensure_collection_sync()

    client.delete_collection.assert_called_once_with(QdrantCorpusRepo.COLLECTION_NAME)
    # _create_collection llama create_collection + sparse_vectors_config, y
    # crea los indices de normas y obras.
    client.create_collection.assert_called_once()
    assert client.create_payload_index.call_count == 11


def test_ensure_collection_is_noop_when_dimension_matches() -> None:
    """Misma dimension -> no recreate, pero SI asegura payload indexes."""
    client = _make_qdrant_client(current_dim=768, collection_exists=True)
    # get_collection debe reportar sparse_vectors ya presentes -> no update_collection.
    info = client.get_collection.return_value
    info.config.params.sparse_vectors = {"text-sparse": MagicMock()}
    repo = _make_repo(client, target_dim=768)

    repo._ensure_collection_sync()

    client.delete_collection.assert_not_called()
    client.create_collection.assert_not_called()
    client.update_collection.assert_not_called()  # ya tenia sparse
    # create_payload_index es idempotente: asegura visibilidad + propietario_id.
    assert client.create_payload_index.call_count >= 2


def test_ensure_collection_no_intenta_agregar_sparse_a_coleccion_existente() -> None:
    """Una colección densa existente se conserva sin migración destructiva."""
    client = _make_qdrant_client(current_dim=768, collection_exists=True)
    repo = _make_repo(client, target_dim=768)

    repo._ensure_collection_sync()

    client.update_collection.assert_not_called()


def test_ensure_collection_creates_new_collection_when_missing() -> None:
    """Si la coleccion NO existe -> la crea sin chequeo de flag."""
    client = _make_qdrant_client(current_dim=None, collection_exists=False)
    repo = _make_repo(client, target_dim=768)

    repo._ensure_collection_sync()

    # _create_collection debe haber sido llamado.
    client.create_collection.assert_called_once()
    client.delete_collection.assert_not_called()
