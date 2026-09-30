"""Adapter: OllamaEmbedder — Embeddings via Ollama /api/embed.

Usa httpx.AsyncClient con pool de conexiones.
Configuracion via Settings (default) o por endpoint (Sprint 2 multi-proveedor).

Robustez: @retry con tenacity para timeouts y network errors (3 intentos,
backoff exponencial). Errores 4xx (Bad Request) no se reintentan: son
deterministicos, no transientes. Hereda de HttpEmbedder.

Prefijos query/document (Plan C Fase 5): algunos modelos requieren un prefijo
al generar embeddings para diferenciar consultas de documentos:
    - bge-m3: 'search_query:' en consultas, 'search_document:' en documentos.
    - qwen3-embedding: instruccion 'Instruct: ...' (solo para consultas).
Este adapter aplica el prefijo de QUERY por defecto al batch. Para indexacion
de documentos, el caller puede setear `query_prefix=False` (no se usa en el
pipeline actual de indexacion, que embeede fragmentos como pasajes neutros).
"""

from __future__ import annotations

from src.adapters.embedding.http_embedder import HttpEmbedder
from src.config import get_settings

# Prefijo de query por modelo (documentado en docs/evaluacion/). Solo los
# modelos que lo requieren aparecen; el resto queda sin prefijo.
_QUERY_PREFIX_POR_MODELO: dict[str, str] = {
    "bge-m3": "search_query: ",
    "bge-m3:latest": "search_query: ",
    "qwen3-embedding": "Instruct: ",
    "qwen3-embedding:latest": "Instruct: ",
}


class OllamaEmbedder(HttpEmbedder):
    """Generador de embeddings usando un servidor Ollama (/api/embed)."""

    embed_path = "/api/embed"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        dim: int | None = None,
        batch_size: int | None = None,
        timeout: float | None = None,
        query_prefix: str | None = None,
    ) -> None:
        settings = get_settings()
        super().__init__(
            base_url=(base_url or settings.ollama_host),
            model=(model or settings.embedding_model_name),
            dim=(dim if dim is not None else settings.embedding_dim),
            batch_size=(batch_size or settings.embedding_text_batch_size),
            timeout=(timeout if timeout is not None else settings.ollama_timeout_seconds),
        )
        # Prefijo de query: explicito > por modelo > ninguno.
        self._query_prefix = (
            query_prefix
            if query_prefix is not None
            else _QUERY_PREFIX_POR_MODELO.get(self._model, "")
        )

    def _prefijar_batch(self, batch: list[str]) -> list[str]:
        if not self._query_prefix:
            return batch
        return [f"{self._query_prefix}{t}" for t in batch]

    def _model_request(self, batch: list[str]) -> dict:
        """Ollama /api/embed usa {model, input}.

        `keep_alive: -1` deja el embedder residente (565 MB): sin esto, el
        `OLLAMA_KEEP_ALIVE` del server también lo descarga y la primera
        consulta tras esa pausa paga la recarga. El modelo grande no manda
        keep_alive, así que se descarga según el default del server.
        """
        return {"model": self._model, "input": batch, "keep_alive": -1}

    def _extract_embeddings(self, data: dict) -> list[list[float]]:
        """Ollama devuelve {'embeddings': [...]}."""
        return data.get("embeddings")


__all__ = ["OllamaEmbedder"]
