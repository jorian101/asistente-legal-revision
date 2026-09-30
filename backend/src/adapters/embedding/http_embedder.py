"""Base clase: HttpEmbedder — patrón común para embedders HTTP.

Encapsula el comportamiento compartido por todos los proveedores de embeddings
por HTTP (Ollama): cliente httpx con pool, reintentos
tenacity para timeouts/network errors, batch de textos con truncado a 8000
chars, y validacion de dimension de cada vector.

Los modelos concretos solo definen:
- `embed_path`: ruta del endpoint de embeddings relativa a base_url.
- `_build_body(batch)` -> dict: cuerpo JSON del request.
- `_parse_response(data, batch_start) -> list[list[float]]`: extrae vectores.
- `_auth_headers()`: headers de autorizacion (dict | None).
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class HttpEmbedder(ABC):
    """Embedder trans-HTTTP: batch + retry + truncado + validacion dim."""

    # 3 intentos, backoff 1s -> 2s -> 4s, solo timeouts y network errors.
    _RETRY = retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )

    # Techo de chars por texto (nomic-embed-text ~8192 tokens; margen seguro).
    MAX_CHARS = 8000

    #: Subclase: ruta del endpoint de embeddings (relativa a base_url).
    embed_path: str = "/embeddings"

    @abstractmethod
    def _model_request(self, batch: list[str]) -> dict:
        """Cuerpo JSON del request. Ej: {'model': self._model, 'input': batch}."""

    def _auth_request(self) -> dict[str, str]:
        """Headers de autorizacion. Por defecto vacio."""
        return {}

    def _prefijar_batch(self, batch: list[str]) -> list[str]:
        """Aplica el prefijo query/document del modelo (Plan C Fase 5).

        Por defecto no hace nada. Los modelos que lo requieren (bge-m3:
        'search_query:', qwen3: 'Instruct:') lo sobrescriben. Se aplica en
        `embed` sobre el batch truncado.
        """
        return batch

    @abstractmethod
    def _extract_embeddings(self, data: dict) -> list[list[float]]:
        """Extrae la lista cruda de vectores sin validar."""

    def __init__(
        self,
        base_url: str,
        model: str,
        dim: int,
        batch_size: int = 64,
        timeout: float = 300.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dim = dim
        self._batch_size = batch_size
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
                limits=limits,
                headers=self._auth_request(),
            )
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Genera embeddings en lotes, truncando a MAX_CHARS."""
        if not texts:
            return []

        client = self._get_client()
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = self._prefijar_batch(
                [t[: self.MAX_CHARS] for t in texts[i : i + self._batch_size]]
            )
            try:
                embeddings = await self._embed_batch(client, batch, i)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                raise RuntimeError(
                    f"{type(self).__name__} no respondio tras 3 intentos "
                    f"(batch starting at {i}, batch_size={len(batch)}): "
                    f"{type(e).__name__}: {e}"
                ) from e
            except httpx.HTTPStatusError as e:
                raise RuntimeError(
                    f"{type(self).__name__} rechazo batch "
                    f"(batch starting at {i}, batch_size={len(batch)}): "
                    f"HTTP {e.response.status_code} - {e.response.text[:200]}"
                ) from e

            all_embeddings.extend(embeddings)

            if i + self._batch_size < len(texts):
                await asyncio.sleep(0.05)

        return all_embeddings

    @_RETRY
    async def _embed_batch(
        self,
        client: httpx.AsyncClient,
        batch: list[str],
        batch_start: int,
    ) -> list[list[float]]:
        """POST a embed_path con retry para transients; 4xx se propaga."""
        resp = await client.post(
            self.embed_path,
            json=self._model_request(batch),
        )
        resp.raise_for_status()
        return self._parse_response(resp.json(), batch_start)

    def _parse_response(self, data: dict, batch_start: int) -> list[list[float]]:
        """Validar dimension y devolver vectores ya ordenados."""
        embeddings = self._extract_embeddings(data)
        if not embeddings or not isinstance(embeddings, list):
            raise RuntimeError(
                f"Respuesta inesperada de {type(self).__name__} (batch {batch_start}): {data}"
            )
        for j, emb in enumerate(embeddings):
            if not isinstance(emb, list):
                raise RuntimeError(
                    f"Embedding {j} del batch {batch_start} no es lista: {type(emb)}"
                )
            if len(emb) != self._dim:
                raise RuntimeError(
                    f"Embedding {j} del batch {batch_start} dimension "
                    f"{len(emb)} != esperada {self._dim}"
                )
        return embeddings

    @abstractmethod
    def _extract_embeddings(self, data: dict) -> list[list[float]]:
        """Extrae la lista cruda de vectors sin validar."""

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> HttpEmbedder:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
