"""Tests del wrapper RerankerWithFallback (F4).

Verifican:
- 5xx / timeout / network -> siguiente endpoint
- 4xx -> propaga inmediatamente (no reintenta)
- Todos transitorios -> propaga el ultimo error
- Lista vacia -> ValueError
- Happy path -> devuelve el del primero

Usan doubles in-line que simulan ser Reranker y arrojan httpx.HTTPStatusError
con mock response (no depende de HTTP real).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from src.adapters.reranker.fallback import RerankerWithFallback


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Crea un HTTPStatusError con mock response para el codigo dado."""
    request = httpx.Request("POST", "http://x/rerank")
    response = httpx.Response(status_code=status_code, request=request)
    return httpx.HTTPStatusError(f"HTTP {status_code}", request=request, response=response)


class FakeReranker:
    """Double que devuelve un resultado fijo o arroja un error configurado."""

    def __init__(
        self,
        result: list[tuple[int, float]] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._result = result or [(0, 1.0)]
        self._exc = exc
        self.rerank = MagicMock(side_effect=self._rerank_impl)
        self.close = MagicMock(side_effect=self._close_impl)

    async def _rerank_impl(self, query, candidates, top_k):  # noqa: ANN001
        if self._exc is not None:
            raise self._exc
        return self._result

    async def _close_impl(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_devuelve_del_primero():
    primary = FakeReranker(result=[(1, 0.9), (0, 0.5)])
    secondary = FakeReranker()
    wrapper = RerankerWithFallback([primary, secondary])

    result = await wrapper.rerank("q", ["a", "b"], 2)

    assert result == [(1, 0.9), (0, 0.5)]
    primary.rerank.assert_called_once()
    secondary.rerank.assert_not_called()


# ---------------------------------------------------------------------------
# Transitorio: 5xx -> siguiente endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_5xx_cae_al_siguiente():
    primary = FakeReranker(exc=_http_status_error(503))
    secondary = FakeReranker(result=[(2, 0.8)])
    wrapper = RerankerWithFallback([primary, secondary])

    result = await wrapper.rerank("q", ["a", "b", "c"], 1)

    assert result == [(2, 0.8)]
    primary.rerank.assert_called_once()
    secondary.rerank.assert_called_once()


@pytest.mark.asyncio
async def test_timeout_cae_al_siguiente():
    primary = FakeReranker(exc=httpx.TimeoutException("timeout"))
    secondary = FakeReranker(result=[(0, 1.0)])
    wrapper = RerankerWithFallback([primary, secondary])

    result = await wrapper.rerank("q", ["a"], 1)

    assert result == [(0, 1.0)]


@pytest.mark.asyncio
async def test_network_error_cae_al_siguiente():
    primary = FakeReranker(exc=httpx.NetworkError("conn refused"))
    secondary = FakeReranker(result=[(0, 1.0)])
    wrapper = RerankerWithFallback([primary, secondary])

    result = await wrapper.rerank("q", ["a"], 1)

    assert result == [(0, 1.0)]


# ---------------------------------------------------------------------------
# No transitorio: 4xx -> propaga
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_4xx_propaga_no_reintenta():
    primary = FakeReranker(exc=_http_status_error(400))
    secondary = FakeReranker()
    wrapper = RerankerWithFallback([primary, secondary])

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await wrapper.rerank("q", ["a"], 1)

    assert exc_info.value.response.status_code == 400
    primary.rerank.assert_called_once()
    secondary.rerank.assert_not_called()


@pytest.mark.asyncio
async def test_404_propaga_no_reintenta():
    primary = FakeReranker(exc=_http_status_error(404))
    secondary = FakeReranker()
    wrapper = RerankerWithFallback([primary, secondary])

    with pytest.raises(httpx.HTTPStatusError):
        await wrapper.rerank("q", ["a"], 1)


# ---------------------------------------------------------------------------
# Todos transitorios -> propaga el ultimo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_todos_transitorios_propaga_ultimo():
    primary = FakeReranker(exc=_http_status_error(503))
    secondary = FakeReranker(exc=httpx.TimeoutException("timeout"))
    tertiary = FakeReranker(exc=httpx.NetworkError("dns"))
    wrapper = RerankerWithFallback([primary, secondary, tertiary])

    with pytest.raises(httpx.NetworkError) as exc_info:
        await wrapper.rerank("q", ["a"], 1)

    assert isinstance(exc_info.value, httpx.NetworkError)
    primary.rerank.assert_called_once()
    secondary.rerank.assert_called_once()
    tertiary.rerank.assert_called_once()


# ---------------------------------------------------------------------------
# Lista vacia -> ValueError
# ---------------------------------------------------------------------------


def test_lista_vacia_levanta_value_error():
    with pytest.raises(ValueError, match="al menos un reranker"):
        RerankerWithFallback([])


# ---------------------------------------------------------------------------
# Cierre: cierra todos los rerankers internos (best-effort)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_cierra_todos():
    primary = FakeReranker()
    secondary = FakeReranker()
    wrapper = RerankerWithFallback([primary, secondary])

    await wrapper.close()

    primary.close.assert_called_once()
    secondary.close.assert_called_once()


# ---------------------------------------------------------------------------
# 5xx en todos menos uno que si funciona -> usa ese
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_5xx_en_primario_y_secundario_usa_terciario():
    primary = FakeReranker(exc=_http_status_error(500))
    secondary = FakeReranker(exc=_http_status_error(503))
    tertiary = FakeReranker(result=[(0, 1.0)])
    wrapper = RerankerWithFallback([primary, secondary, tertiary])

    result = await wrapper.rerank("q", ["a"], 1)

    assert result == [(0, 1.0)]
    primary.rerank.assert_called_once()
    secondary.rerank.assert_called_once()
    tertiary.rerank.assert_called_once()
