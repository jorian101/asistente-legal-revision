"""Interactor: VerEstadoIndexacion — Caso de uso de diagnóstico de indexación.

Devuelve el estado de indexación de una norma específica (HU-04): si está
indexada, quién la indexó y cuántos fragmentos tiene. Útil para el admin antes
de reindexar o reconciliar.

Clean Architecture: dominio puro, sin I/O directo. Puertos inyectados.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.fragmento_repo import FragmentoRepo
from src.application.ports.norma_repo import NormaRepo


@dataclass(slots=True)
class EstadoIndexacionDTO:
    """DTO de salida: estado de indexación de una norma."""

    norma_id: int
    abreviatura: str
    indexado: bool
    indexado_por: int | None
    fragmentos_count: int


class VerEstadoIndexacion:
    """Caso de uso: Ver estado de indexación de una norma."""

    def __init__(self, norma_repo: NormaRepo, fragmento_repo: FragmentoRepo) -> None:
        self._norma_repo = norma_repo
        self._fragmento_repo = fragmento_repo

    async def ejecutar(self, norma_id: int) -> EstadoIndexacionDTO | None:
        """Devuelve el estado de indexación. None si la norma no existe."""
        norma = await self._norma_repo.get_by_id(norma_id)
        if norma is None:
            return None
        fragmentos_count = await self._fragmento_repo.count_by_norma(norma_id)
        return EstadoIndexacionDTO(
            norma_id=norma_id,
            abreviatura=norma.abreviatura,
            indexado=norma.indexado,
            indexado_por=norma.indexado_por,
            fragmentos_count=fragmentos_count,
        )
