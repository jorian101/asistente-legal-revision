"""Tests del truncado a max_chars en OllamaEmbedder.

blindan:
- Textos <= 8000 chars se envian tal cual (sin truncar).
- Textos > 8000 chars se truncan a 8000 antes de enviar.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.ollama.ollama_embedder import OllamaEmbedder


def _patch_embedder_with_client(embedder: OllamaEmbedder, client: AsyncMock) -> None:
    """Inyecta un cliente httpx mockeado sin rebuild automatico."""
    client.is_closed = False
    embedder._client = client


@pytest.mark.asyncio
async def test_text_shorter_than_8000_chars_unmodified() -> None:
    """Textos cortos pasan sin modificar al batch."""
    embedder = OllamaEmbedder(batch_size=2, timeout=5.0)
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

    short = "a" * 1000
    await embedder.embed([short, "b" * 3000])

    assert captured["batch"] is not None
    assert len(captured["batch"][0]) == 1000
    assert len(captured["batch"][1]) == 3000


@pytest.mark.asyncio
async def test_text_longer_than_8000_chars_is_truncated() -> None:
    """Texto > 8000 chars -> se trunca a 8000 antes de enviar a Ollama."""
    embedder = OllamaEmbedder(batch_size=1, timeout=5.0)
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

    long_text = "x" * 10000
    await embedder.embed([long_text])

    assert captured["batch"] is not None
    assert len(captured["batch"][0]) == 8000
