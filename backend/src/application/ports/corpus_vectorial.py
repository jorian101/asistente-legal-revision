"""Puerto: CorpusRepoVectorial — Interfaz para persistencia vectorial en Qdrant.

    Responsabilidades:
    - Crear/verificar la colección vectorial compartida con HNSW config
- Upsert batch de puntos con vectores + payload
- Búsqueda semántica (k-NN) con filtros por payload
- Búsqueda híbrida (denso + disperso, RRF server-side) — Sprint 3, D1
- Borrado por norma_id (re-indexación)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from src.domain.value_objects import ScoredPoint, SparseVector


class CorpusRepoVectorial(Protocol):
    """Protocolo para repositorio vectorial del corpus jurídico."""

    async def ensure_collection(self) -> None:
        """Crea la colección `corpus_juridico` si no existe.

        Configuración:
        - Vector size: EMBEDDING_DIM (ej: 768)
        - Distance: Cosine
        - HNSW: m=16, ef_construct=100 (balance precisión/velocidad)
        - Payload indexes: norma_id, abreviatura, numero_articulo, tipo_chunk
        """
        ...

    async def upsert_corpus(self, points: list[dict[str, Any]]) -> None:
        """Inserta o actualiza puntos en lote.

        Args:
            points: Lista de dicts con claves:
                - id: str (UUIDv4)
                - vector: list[float] (dimensión EMBEDDING_DIM)
                - payload: dict (ver esquema abajo)

        Esquema payload esperado (norma u obra):
        {
            "tipo_fuente": "norma" | "obra",
            "norma_id": int | None,
            "obra_id": int | None,
            "expediente_id": int | None,
            "propietario_id": int | None,
            "visibilidad": "privado" | "publicado" | None,
            "abreviatura": "CPPM" | "CPM" | ...,
            "numero_articulo": int,
            "texto": str,
            "tipo_chunk": "articulo_simple" | "articulo_multiparagrafo" | ...,
            "nivel_jerarquico": 4,
            "padre_ref_key": "CPPM_184_MASTER" | None,
            "metadatos": { ... }
        }
        """
        ...

    async def search(
        self,
        vector: list[float],
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Búsqueda k-NN semántica con filtros opcionales.

        Args:
            vector: Vector de consulta (query embedding).
            limit: Número máximo de resultados.
            filters: Filtros por payload (ej: {"abreviatura": "CPPM"}).

        Returns:
            Lista de hits con: id, score, payload.
        """
        ...

    async def delete_by_norma(self, norma_id: int) -> None:
        """Elimina todos los puntos de una norma (para re-indexación).

        Args:
            norma_id: ID de la norma en PostgreSQL.
        """
        ...

    async def delete_by_obra(self, obra_id: int) -> None:
        """Elimina los puntos vectoriales asociados a una obra."""
        ...

    async def actualizar_payload_obra(self, obra_id: int, payload: dict) -> None:
        """Actualiza campos del payload de los puntos de una obra (p. ej. su categoría)."""
        ...

    async def actualizar_payload_norma(self, norma_id: int, payload: dict) -> None:
        """Actualiza campos del payload de los puntos de una norma/fuente."""
        ...

    async def actualizar_visibilidad_obra(self, obra_id: int, visibilidad: str) -> None:
        """Actualiza el payload `visibilidad` de los puntos de una obra.

        El filtro de privacidad (Regla 4) lee este payload: debe reflejar
        el `estado_visibilidad` vigente en PostgreSQL.
        """
        ...

    async def search_hybrid(
        self,
        dense_vector: list[float],
        sparse_vector: SparseVector,
        alpha: float,
        filters: dict[str, Any],
        limit: int,
    ) -> list[ScoredPoint]:
        """Búsqueda híbrida (denso + disperso) con RRF server-side.

        Regla 4 Trail of Bits (BLOQUEANTE): `filters` SIEMPRE debe incluir
        `usuario_id` (de quién es la consulta). El adapter aplica el filtro de
        privacidad de obrados de forma OBLIGATORIA — nunca es opcional. Si
        falta `usuario_id` → ValueError.

        Args:
            dense_vector: Embedding denso de la query.
            sparse_vector: Vector disperso (BM25) de la query.
            alpha: Ponderación denso/lexico (reservado; RRF puro por ahora).
            filters: Filtros de payload + usuario_id (Regla 4).
            limit: Número máximo de resultados finales tras fusión.

        Returns:
            Lista de ScoredPoint con scores de la fusión RRF.
        """
        ...

    async def search_dense(
        self,
        dense_vector: list[float],
        filters: dict[str, Any],
        limit: int,
    ) -> list[ScoredPoint]:
        """Búsqueda k-NN densa (fallback sin sparse vectors).

        Regla 4 Trail of Bits (BLOQUEANTE): mismo requisito obligatorio de
        `usuario_id` en `filters` que `search_hybrid`.

        Args:
            dense_vector: Embedding denso de la query.
            filters: Filtros de payload + usuario_id (Regla 4).
            limit: Número máximo de resultados.

        Returns:
            Lista de ScoredPoint con scores de similitud densa.
        """
        ...

    async def list_all_ids(self) -> list[str]:
        """Scroll de todos los IDs de puntos activos en la colección."""
        ...

    async def delete_many(self, ids: list[str]) -> None:
        """Elimina múltiples puntos por ID (uuid string)."""
        ...

    async def close(self) -> None:
        """Cierra cliente Qdrant."""
        ...


class CorpusRepoVectorialABC(ABC):
    """Base abstracta para implementaciones concretas."""

    @abstractmethod
    async def ensure_collection(self) -> None: ...

    @abstractmethod
    async def upsert_corpus(self, points: list[dict[str, Any]]) -> None: ...

    @abstractmethod
    async def search(
        self,
        vector: list[float],
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def delete_by_norma(self, norma_id: int) -> None: ...

    @abstractmethod
    async def delete_by_obra(self, obra_id: int) -> None: ...

    @abstractmethod
    async def search_hybrid(
        self,
        dense_vector: list[float],
        sparse_vector: SparseVector,
        alpha: float,
        filters: dict[str, Any],
        limit: int,
    ) -> list[ScoredPoint]: ...

    @abstractmethod
    async def search_dense(
        self,
        dense_vector: list[float],
        filters: dict[str, Any],
        limit: int,
    ) -> list[ScoredPoint]: ...

    @abstractmethod
    async def close(self) -> None: ...
