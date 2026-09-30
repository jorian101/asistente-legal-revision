"""Puerto: Embedder — Interfaz para generación de embeddings vectoriales.

Implementaciones:
- OllamaEmbedder (infra): usa Ollama /api/embed
- SentenceTransformersEmbedder (futuro): modelo local
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol


class Embedder(Protocol):
    """Protocolo para generadores de embeddings."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Genera embeddings para una lista de textos.

        Args:
            texts: Lista de strings a vectorizar.

        Returns:
            Lista de vectores (list[float]), uno por texto de entrada.
            Cada vector debe tener la dimensión configurada (ej: 768 para nomic-embed-text).

        Raises:
            RuntimeError: Si el servicio de embeddings no está disponible.
        """
        ...

    async def close(self) -> None:
        """Cierra conexiones/recursos (ej: httpx.AsyncClient)."""
        ...


class EmbedderABC(ABC):
    """Base abstracta para implementaciones concretas (herencia clásica)."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Genera embeddings para una lista de textos."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Cierra recursos (clientes HTTP, pools, etc.)."""
        ...
