"""Puerto: Reranker — Interfaz para reranking de candidatos de recuperación.

Fase 3 del pipeline RAG (decision D10 del plan Sprint 3): el proveedor del
cross-encoder es dinamico multi-endpoint, igual que los embeddings
(RERANKER_ENDPOINTS en config.py). El adapter concreto (HttpReranker)
recibe base_url+model+api_key por constructor y es agnostico del proveedor.

Implementaciones:
- HttpReranker (infra): llama a un endpoint HTTP /rerank local.
  Retry con backoff para transients.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol


class Reranker(Protocol):
    """Protocolo para rerankers de cross-encoder.

    Recibe la query original y los textos candidatos, retorna una lista de
    (indice_original, score) ordenada desc por relevancia rerankeada.
    """

    async def rerank(
        self,
        query: str,
        candidates: list[str],
        top_k: int,
    ) -> list[tuple[int, float]]:
        """Rerankear candidatos respecto a la query.

        Args:
            query: Texto de la consulta original del usuario.
            candidates: Textos de los fragmentos candidatos (orden preservado).
            top_k: Numero maximo de resultados a retornar.

        Returns:
            Lista de (indice_original, score) ordenada por score desc.
            El indice_original referenciado es la posicion en `candidates`.
        """
        ...

    async def close(self) -> None:
        """Cierra conexiones/recursos (ej: httpx.AsyncClient)."""
        ...


class RerankerABC(ABC):
    """Base abstracta para implementaciones concretas (herencia clasica)."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[str],
        top_k: int,
    ) -> list[tuple[int, float]]:
        """Rerankear candidatos respecto a la query."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Cierra recursos (clientes HTTP, pools, etc.)."""
        ...
