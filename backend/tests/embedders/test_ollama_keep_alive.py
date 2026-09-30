"""El OllamaEmbedder manda keep_alive: -1 para quedar residente (565 MB)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.ollama.ollama_embedder import OllamaEmbedder


@pytest.mark.asyncio
async def test_ollama_embedder_manda_keep_alive_negativo() -> None:
    """El body de /api/embed incluye keep_alive: -1 (residente)."""
    embedder = OllamaEmbedder(model="nomic-embed-text", batch_size=2, timeout=5.0)
    capturado: dict = {}

    async def fake_post(url: str, json: dict) -> MagicMock:
        capturado.update(json)
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        n = len(json["input"])
        resp.json = lambda: {"embeddings": [[0.0] * 768 for _ in range(n)]}
        return resp

    client = AsyncMock()
    client.is_closed = False
    client.post = fake_post
    embedder._client = client

    await embedder.embed(["consulta"])

    assert capturado["keep_alive"] == -1
