"""Value objects de dominio compartidos por el pipeline RAG (Sprint 3+).

Contienen ScoredPoint (resultado de búsqueda vectorial) y SparseVector
(representación de vector disperso para BM25 server-side en Qdrant).

Regla Clean Architecture: dataclasses puras, sin qdrant-client ni SQLAlchemy.
Los adapters convierten entre estos value objects y los tipos del SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SparseVector:
    """Vector disperso (índices + valores) para búsqueda léxica BM25.

    Reemplaza a `models.SparseVector` de qdrant-client en los ports y en el
    dominio, para no acoplar la capa core al SDK. El adapter lo traduce.
    """

    indices: tuple[int, ...]
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ScoredPoint:
    """Resultado de una búsqueda vectorial con su score de similitud.

    Atributos:
        qdrant_id: ID del punto en Qdrant (uuid string del fragmento).
        score: Score de similitud (según la distancia configurada, Cosine).
        payload: Payload almacenado en el punto (norma_id, texto, metadatos...).
    """

    qdrant_id: str
    score: float
    payload: dict[str, Any]
