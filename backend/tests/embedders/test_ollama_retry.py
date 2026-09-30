"""Tests del retry tenacity en OllamaEmbedder.

Cubren 3 invariantes contractuales:
- Timeouts y network errors son transitorios -> reintentar hasta 3 veces (3s -> 2s -> 1s backoff).
- 4xx (HTTPStatusError) NO son transitorios -> propagar sin reintentar.
- Tras 3 intentos fallidos -> propagar la excepcion transitoria.

Los tests parchean `tenacity.nap.time.sleep` para eliminar esperas reales
(multiplier=1, min=1, max=4 en el codigo de produccion).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.adapters.ollama.ollama_embedder import OllamaEmbedder


@pytest.fixture
def fast_tenacity():
    """Parchea tenacity para que NO espere entre retries (tests rapidos)."""
    # tenacity usa tenacity.nap.time.sleep para esperar entre intentos.
    # Patch globalmente para que no haya esperas reales durante los tests.
    with patch("tenacity.nap.time.sleep", new=MagicMock()):
        yield


def _make_good_response(dim: int = 768) -> MagicMock:
    """Mock de respuesta exitosa de Ollama /api/embed."""
    resp = MagicMock()
    resp.raise_for_status = lambda: None
    resp.json = lambda: {"embeddings": [[0.0] * dim, [0.1] * dim]}
    return resp


def _patch_embedder_with_client(embedder: OllamaEmbedder, client: AsyncMock) -> None:
    """Inyecta un cliente httpx mockeado en el embedder.

    `_get_client` chequea `self._client.is_closed` para decidir si rebuild.
    Con AsyncMock(), `is_closed` se auto-mockea como MagicMock (truthy), lo que
    hace que `if ... or self._client.is_closed:` siempre entre al rebuild, ignorando
    nuestro mock. Forzamos `is_closed = False` para que use el inyectado.
    """
    client.is_closed = False
    embedder._client = client


@pytest.mark.asyncio
async def test_retry_transient_on_timeout_then_succeeds(fast_tenacity: None) -> None:
    """2 ReadTimeouts seguidos de exito -> reintenta 3 veces y devuelve embeddings."""
    embedder = OllamaEmbedder(batch_size=2, timeout=5.0)
    call_count = {"n": 0}

    async def fake_post(url: str, json: dict) -> MagicMock:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise httpx.ReadTimeout("simulated timeout")
        return _make_good_response()

    client = AsyncMock()
    client.post = fake_post
    _patch_embedder_with_client(embedder, client)

    result = await embedder.embed(["hola", "mundo"])

    assert call_count["n"] == 3, f"esperaba 3 POSTs (2 fallos + 1 ok), vi {call_count['n']}"
    assert len(result) == 2
    assert len(result[0]) == 768


@pytest.mark.asyncio
async def test_no_retry_on_4xx_http_status_error(fast_tenacity: None) -> None:
    """4xx NO se reintenta -> RuntimeError inmediato tras 1 sola llamada."""
    embedder = OllamaEmbedder(batch_size=2, timeout=5.0)
    call_count = {"n": 0}

    bad_resp = MagicMock()
    bad_resp.status_code = 400
    bad_resp.text = "Bad Request: input too long"

    def raise_bad_request() -> None:
        raise httpx.HTTPStatusError("400", request=MagicMock(), response=bad_resp)

    bad_resp.raise_for_status = raise_bad_request

    async def fake_post(url: str, json: dict) -> MagicMock:
        call_count["n"] += 1
        return bad_resp

    client = AsyncMock()
    client.post = fake_post
    _patch_embedder_with_client(embedder, client)

    with pytest.raises(RuntimeError) as exc_info:
        await embedder.embed(["hola", "mundo"])

    assert call_count["n"] == 1, f"4xx NO deberia reintentar; vi {call_count['n']} intentos"
    assert "400" in str(exc_info.value) or "rechazo" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_retry_stops_after_3_attempts_then_raises(fast_tenacity: None) -> None:
    """3 timeouts seguidos -> RuntimeError propagado tras agotar intentos."""
    embedder = OllamaEmbedder(batch_size=2, timeout=5.0)
    call_count = {"n": 0}

    async def fake_post(url: str, json: dict) -> MagicMock:
        call_count["n"] += 1
        raise httpx.ReadTimeout("persistent timeout")

    client = AsyncMock()
    client.post = fake_post
    _patch_embedder_with_client(embedder, client)

    with pytest.raises(RuntimeError) as exc_info:
        await embedder.embed(["hola", "mundo"])

    assert call_count["n"] == 3, f"esperaba exactamente 3 intentos, vi {call_count['n']}"
    assert "3 intentos" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_no_retry_on_network_error_then_succeeds(fast_tenacity: None) -> None:
    """Network errors (httpx.NetworkError — incluye RemoteProtocolError, etc.) se reintentan.

    1 NetworkError seguido de exito -> 2 POSTs, retorna embeddings.
    """
    embedder = OllamaEmbedder(batch_size=2, timeout=5.0)
    call_count = {"n": 0}

    async def fake_post(url: str, json: dict) -> MagicMock:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.ConnectError("simulated connection refused")
        return _make_good_response()

    client = AsyncMock()
    client.post = fake_post
    _patch_embedder_with_client(embedder, client)

    result = await embedder.embed(["hola", "mundo"])

    assert call_count["n"] == 2
    assert len(result) == 2
