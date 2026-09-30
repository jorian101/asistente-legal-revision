"""Use case: EliminarBorrador (CRITICAL #3 — soft delete).

Marca activo=False un borrador. Regla 7 (BLOQUEANTE): solo el propietario
puede eliminar SU borrador — el repo filtra por propietario_id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports.borrador_repo import BorradorRepo


async def eliminar_borrador(
    repo: BorradorRepo,
    *,
    borrador_id: int,
    propietario_id: int,
) -> bool:
    """Soft delete de un borrador del propietario (Regla 7).

    Returns:
        True si se elimino; False si no existe o es de otro usuario.
    """
    return await repo.eliminar_soft(
        borrador_id=borrador_id,
        propietario_id=propietario_id,
    )
