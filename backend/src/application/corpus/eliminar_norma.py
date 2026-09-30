"""Use case: EliminarNorma (CRITICAL #3 — soft delete).

Marca activo=False una norma del corpus (solo admin). No borra fisicamente:
los fragmentos indexados en Qdrant/PG se conservan para auditoria.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports.norma_repo import NormaRepo


async def eliminar_norma(repo: NormaRepo, *, norma_id: int) -> bool:
    """Soft delete de una norma (activo=False). True si existia y activa."""
    return await repo.eliminar_soft(norma_id=norma_id)
