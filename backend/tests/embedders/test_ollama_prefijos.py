"""Tests del prefijo query/document por modelo en OllamaEmbedder (Plan C F5).

blinda:
- bge-m3 y qwen3-embedding reciben el prefijo de query correspondiente.
- Modelos sin prefijo (nomic-embed-text) no se modifican.
- El prefijo explícito por constructor tiene prioridad sobre el del modelo.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.ollama.ollama_embedder import OllamaEmbedder


def _patch_embedder_with_client(embedder: OllamaEmbedder, client: AsyncMock) -> None:
    client.is_closed = False
    embedder._client = client


@pytest.mark.asyncio
async def test_bge_m3_recibe_prefijo_search_query() -> None:
    """bge-m3: el batch se prefija con 'search_query: ' (query)."""
    embedder = OllamaEmbedder(model="bge-m3", dim=1024, batch_size=2, timeout=5.0)
    captured = {"batch": None}

    async def fake_post(url: str, json: dict) -> MagicMock:
        captured["batch"] = json["input"]
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        n = len(json["input"])
        resp.json = lambda: {"embeddings": [[0.0] * 1024 for _ in range(n)]}
        return resp

    client = AsyncMock()
    client.post = fake_post
    _patch_embedder_with_client(embedder, client)

    await embedder.embed(["consulta sobre sentencia"])

    assert captured["batch"][0] == "search_query: consulta sobre sentencia"


@pytest.mark.asyncio
async def test_qwen3_recibe_prefijo_instruct() -> None:
    """qwen3-embedding: el batch se prefija con 'Instruct: ' (query)."""
    embedder = OllamaEmbedder(model="qwen3-embedding", dim=1024, batch_size=2, timeout=5.0)
    captured = {"batch": None}

    async def fake_post(url: str, json: dict) -> MagicMock:
        captured["batch"] = json["input"]
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        n = len(json["input"])
        resp.json = lambda: {"embeddings": [[0.0] * 1024 for _ in range(n)]}
        return resp

    client = AsyncMock()
    client.post = fake_post
    _patch_embedder_with_client(embedder, client)

    await embedder.embed(["consulta"])

    assert captured["batch"][0] == "Instruct: consulta"


@pytest.mark.asyncio
async def test_nomic_sin_prefijo() -> None:
    """nomic-embed-text (actual): el batch NO se modifica."""
    embedder = OllamaEmbedder(model="nomic-embed-text", batch_size=2, timeout=5.0)
    captured = {"batch": None}

    async def fake_post(url: str, json: dict) -> MagicMock:
        captured["batch"] = json["input"]
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        n = len(json["input"])
        resp.json = lambda: {"embeddings": [[0.0] * 768 for _ in range(n)]}
        return resp

    client = AsyncMock()
    client.post = fake_post
    _patch_embedder_with_client(embedder, client)

    await embedder.embed(["consulta sin prefijo"])

    assert captured["batch"][0] == "consulta sin prefijo"


@pytest.mark.asyncio
async def test_prefijo_explicito_tiene_prioridad() -> None:
    """El prefijo pasado por constructor gana al derivado del modelo."""
    embedder = OllamaEmbedder(
        model="bge-m3",
        query_prefix="custom-query: ",
        dim=1024,
        batch_size=2,
        timeout=5.0,
    )
    captured = {"batch": None}

    async def fake_post(url: str, json: dict) -> MagicMock:
        captured["batch"] = json["input"]
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        n = len(json["input"])
        resp.json = lambda: {"embeddings": [[0.0] * 1024 for _ in range(n)]}
        return resp

    client = AsyncMock()
    client.post = fake_post
    _patch_embedder_with_client(embedder, client)

    await embedder.embed(["consulta"])

    assert captured["batch"][0] == "custom-query: consulta"
