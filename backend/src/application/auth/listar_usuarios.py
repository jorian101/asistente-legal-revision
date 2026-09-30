"""Use case: Listar usuarios (admin only).

Sprint 1 Auth (plan v3). Admin lista todos los usuarios para gestion.

Precondiciones:
- Solo admin puede ejecutar (validado por require_admin en router).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports.auth_repository import AuthRepository
    from src.domain.entities.usuario import Usuario


async def execute(auth_repo: AuthRepository) -> list[Usuario]:
    """Lista todos los usuarios ordenados por carnet.

    Args:
        auth_repo: AuthRepository.

    Returns:
        Lista de usuarios (sin password_hash expuesto en el router).
    """
    return await auth_repo.listar_usuarios()
