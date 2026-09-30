"""Interactor: ReconciliarCorpus — Job de reconciliación offline (Regla 3).

Detecta fragmentos Qdrant huérfanos (sin FK en PostgreSQL) y los elimina
del vector store. No corre en el upload — se invoca manualmente desde
el admin o programado como cron.

Clean Architecture: dominio puro, sin I/O directo. Puertos inyectados.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.corpus_vectorial import CorpusRepoVectorial
from src.application.ports.fragmento_repo import FragmentoRepo


@dataclass(slots=True)
class ReconciliacionResult:
    """DTO de salida: conteo de la reconciliación."""

    pg_count: int
    qdrant_count: int
    huerfanos_eliminados: int


class ReconciliarCorpus:
    """Caso de uso: detectar y eliminar fragmentos Qdrant huérfanos.

    Recorre las colecciones dadas (N1 corpus_juridico, N2 jurisprudencia,
    N3 doctrina): PG es la verdad compartida (todos los fragmentos viven
    en una sola tabla), cada colección se compara contra ese conjunto.
    """

    def __init__(
        self,
        fragmento_repo: FragmentoRepo,
        vector_repo: CorpusRepoVectorial | list[CorpusRepoVectorial],
    ) -> None:
        self._fragmento_repo = fragmento_repo
        self._vector_repos = vector_repo if isinstance(vector_repo, list) else [vector_repo]

    async def ejecutar(self) -> ReconciliacionResult:
        pg_ids = set(await self._fragmento_repo.list_all_qdrant_ids())
        total_qdrant = 0
        total_huerfanos = 0
        for repo in self._vector_repos:
            qdrant_ids = set(await repo.list_all_ids())
            huerfanos = qdrant_ids - pg_ids
            if huerfanos:
                await repo.delete_many(list(huerfanos))
            total_qdrant += len(qdrant_ids)
            total_huerfanos += len(huerfanos)

        return ReconciliacionResult(
            pg_count=len(pg_ids),
            qdrant_count=total_qdrant,
            huerfanos_eliminados=total_huerfanos,
        )
