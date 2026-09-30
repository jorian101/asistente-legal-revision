"""Use case: EliminarExpediente (CRITICAL #3 — soft delete).

Archiva el expediente (estado='archivado') usando el mecanismo existente
del modelo. No borra fisicamente: obras y borradores se conservan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports.expediente_repo import ExpedienteRepo


async def eliminar_expediente(repo: ExpedienteRepo, *, expediente_id: int) -> bool:
    """Soft delete: cambia estado a 'archivado'. True si existia y estaba activo."""
    actualizado = await repo.actualizar_estado(expediente_id, "archivado")
    return actualizado is not None
