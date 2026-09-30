"""Tests del adapter HttpReranker (multi-proveedor, decision D10).

Cubren el contrato del puerto Reranker:
- rerank ordena desc por relevance_score.
- rerank trunca a top_k.
- rerank reintenta (3 veces) ante 503 transients y propaga RuntimeError.
- rerank con candidates vacios devuelve [].
- parseo robusto de {"results": [{"index","relevance_score"}]}.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.adapters.reranker.http_reranker import HttpReranker

QUERY = "¿és delito la desobediencia militar?"
CANDIDATES = [
    "Art 1 CP. Desobedencia ...",
    "Art 2 CP. Otro articulo.",
    "Art 3 CP. Insubordinacion.",
]
RESP = {
    "results": [
        {"index": 1, "relevance_score": 0.12},
        {"index": 2, "relevance_score": 0.95},
        {"index": 0, "relevance_score": 0.71},
    ]
}


@pytest.mark.asyncio
async def test_reranker_returns_sorted_by_score_desc() -> None:
    """El reranker ordena desc por relevance_score."""
    reranker = HttpReranker(base_url="http://test", model="bge-reranker-v2-m3")
    with patch.object(
        reranker, "_rerank_request", new=AsyncMock(return_value=HttpReranker._parse_response(RESP))
    ):
        out = await reranker.rerank(QUERY, CANDIDATES, top_k=10)

    indices = [idx for idx, _ in out]
    scores = [s for _, s in out]
    assert scores == sorted(scores, reverse=True)
    assert indices[0] == 2  # el de mayor score en RESP


@pytest.mark.asyncio
async def test_reranker_top_k_truncates() -> None:
    """top_k trunca el resultado."""
    reranker = HttpReranker(base_url="http://test", model="m")
    with patch.object(
        reranker, "_rerank_request", new=AsyncMock(return_value=HttpReranker._parse_response(RESP))
    ):
        out = await reranker.rerank(QUERY, CANDIDATES, top_k=2)

    assert len(out) == 2
    assert out[0][0] == 2  # top 1


@pytest.mark.asyncio
async def test_reranker_empty_candidates_returns_empty() -> None:
    """Candidates vacios -> [] sin llamar al endpoint."""
    reranker = HttpReranker(base_url="http://test", model="m")
    out = await reranker.rerank(QUERY, [], top_k=5)
    assert out == []


@pytest.mark.asyncio
async def test_reranker_retry_on_transient_then_raises_runtime() -> None:
    """3 intentos frente a timeouts proc(RuntimeError tras agotar retries)."""
    reranker = HttpReranker(base_url="http://test", model="m")
    err = httpx.ConnectError("boom")
    with (
        patch.object(reranker, "_rerank_request", new=AsyncMock(side_effect=err)),
        pytest.raises(RuntimeError, match="no respondio"),
    ):
        await reranker.rerank(QUERY, CANDIDATES, top_k=3)


@pytest.mark.asyncio
async def test_reranker_http_status_error_raises_runtime() -> None:
    """Errores 4xx/5xx se envuelven en RuntimeError con codigo HTTP."""
    reranker = HttpReranker(base_url="http://test", model="m")
    request = httpx.Request("POST", "http://test/rerank")
    resp = httpx.Response(status_code=400, request=request)
    err = httpx.HTTPStatusError("", request=request, response=resp)
    with (
        patch.object(reranker, "_rerank_request", new=AsyncMock(side_effect=err)),
        pytest.raises(RuntimeError, match="400"),
    ):
        await reranker.rerank(QUERY, CANDIDATES, top_k=3)


def test_parse_response_rejects_missing_results() -> None:
    """Respuesta sin 'results' -> RuntimeError."""
    with pytest.raises(RuntimeError):
        HttpReranker._parse_response({"foo": []})


def test_parse_response_rejects_incomplete_entry() -> None:
    """Entrada sin index o relevance_score -> RuntimeError."""
    bad = {"results": [{"index": 0}]}  # sin relevance_score
    with pytest.raises(RuntimeError):
        HttpReranker._parse_response(bad)


def test_parse_response_sorts_desc_defensively() -> None:
    """Aunque el endpoint devuelva desordenado, _parse_response ordena."""
    data = {"results": [{"index": 0, "relevance_score": 0.1}, {"index": 1, "relevance_score": 0.9}]}
    out = HttpReranker._parse_response(data)
    assert out[0][0] == 1


def test_get_client_sets_authorization_header_when_api_key() -> None:
    """Si se pasa api_key, el cliente HTTP incluye Authorization Bearer."""
    reranker = HttpReranker(base_url="http://test", model="m", api_key="secret")
    client = reranker._get_client()
    assert client.headers["Authorization"] == "Bearer secret"
