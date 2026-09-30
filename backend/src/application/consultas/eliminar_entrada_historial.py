"""Use case: EliminarEntradaHistorial (CRITICAL #4).

Soft delete de una entrada del historial de consultas. Regla 4 (BLOQUEANTE):
cada usuario solo elimina SU propio historial — el repo filtra por
usuario_id en el UPDATE activo=False.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports.consulta_historial_repo import ConsultaHistorialRepo


async def eliminar_entrada_historial(
    repo: ConsultaHistorialRepo,
    *,
    historial_id: int,
    usuario_id: int,
) -> bool:
    """Marca activo=False una entrada de historial del usuario (soft delete).

    Args:
        repo: ConsultaHistorialRepo.
        historial_id: ID de la entrada a eliminar.
        usuario_id: OBLIGATORIO (Regla 4 — solo el propietario).

    Returns:
        True si se elimino; False si la entrada no existe o no es del usuario.

    Nota: soft delete — no borra la fila (se conserva para auditoria/KPIs).
    """
    return await repo.eliminar_soft(
        historial_id=historial_id,
        usuario_id=usuario_id,
    )
