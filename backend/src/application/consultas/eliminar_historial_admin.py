"""Use case: EliminarHistorialAdmin (solo admin).

Soft delete de una entrada del historial de consultas SIN chequeo de
propietario (el admin puede auditar/limpiar cualquier entrada). Conserva la
fila (activo=False) para auditoria/KPIs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports.consulta_historial_repo import ConsultaHistorialRepo


async def execute(repo: ConsultaHistorialRepo, *, historial_id: int) -> bool:
    """Marca activo=False una entrada de historial (soft delete, admin).

    Returns:
        True si existia una entrada activa y se elimino; False si no existe.
    """
    return await repo.eliminar_soft_admin(historial_id=historial_id)
