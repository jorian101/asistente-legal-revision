"""Adapter: HttpReranker — Reranker de cross-encoder via HTTP (multi-proveedor).

Implementa el puerto application.ports.Reranker. Recibe base_url + model +
api_key por constructor (endpoint-agnostico) — la factory get_reranker() en
dependencies.py selecciona el endpoint de RERANKER_ENDPOINTS.

Decision D10 (plan Sprint 3): el proveedor del reranker es dinamico, igual
que los embeddings. El adapter no conoce el proveedor; solo habla el contrato
/rerank.

Contrato del endpoint /rerank:
    Request:  {"model": "...", "query": "...", "documents": ["...", ...]}
    Response: {"results": [{"index": int, "relevance_score": float}, ...]}

Robustez: @retry tenacity para timeouts y network errors (3 intentos, backoff
exponencial). Errores 4xx (Bad Request) no se reintentan: deterministicos.
"""

from __future__ import annotations

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.application.ports.reranker import Reranker

# 3 intentos, backoff 1s -> 2s -> 4s, solo timeouts y network errors.
_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    reraise=True,
)


class HttpReranker(Reranker):
    """Reranker HTTP (cross-encoder) endpoint-agnostico (decision D10).

    El endpoint /rerank es endpoint-agnóstico (contrato HTTP).
    La factory get_reranker() resuelve el proveedor desde RERANKER_ENDPOINTS.
    """

    RERANK_PATH = "/rerank"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 300.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
                limits=limits,
                headers=headers,
            )
        return self._client

    @_RETRY
    async def _rerank_request(self, query: str, candidates: list[str]) -> list[tuple[int, float]]:
        """POST a /rerank con retry para transients; 4xx se propaga."""
        client = self._get_client()
        resp = await client.post(
            self.RERANK_PATH,
            json={
                "model": self._model,
                "query": query,
                "documents": candidates,
            },
        )
        resp.raise_for_status()
        return self._parse_response(resp.json())

    @staticmethod
    def _parse_response(data: dict) -> list[tuple[int, float]]:
        """Parsea {"results": [{"index", "relevance_score"}, ...]} -> tuples."""
        results = data.get("results")
        if not results or not isinstance(results, list):
            raise RuntimeError(f"Respuesta inesperada del reranker: {str(data)[:200]}")
        ranked: list[tuple[int, float]] = []
        for r in results:
            idx = r.get("index")
            score = r.get("relevance_score")
            if idx is None or score is None:
                raise RuntimeError(f"Entrada incompleta del reranker (sin index/score): {r}")
            ranked.append((int(idx), float(score)))
        # Ordenar desc por score (defensa: el endpoint deberia ya venir ordenado).
        ranked.sort(key=lambda t: t[1], reverse=True)
        return ranked

    async def rerank(
        self,
        query: str,
        candidates: list[str],
        top_k: int,
    ) -> list[tuple[int, float]]:
        """Rerankear y truncar a top_k resultados."""
        if not candidates:
            return []
        try:
            ranked = await self._rerank_request(query, candidates)
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            raise RuntimeError(
                f"{type(self).__name__} no respondio tras 3 intentos "
                f"({len(candidates)} candidatos): {type(e).__name__}: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"{type(self).__name__} rechazo el rerank: "
                f"HTTP {e.response.status_code} - {e.response.text[:200]}"
            ) from e
        return ranked[:top_k]

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
