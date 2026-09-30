"""Use case: Reset de password forzado por admin (HU-02).

Sprint 1 Auth (plan v3). Sistema OFFLINE sin SMTP: solo Admin puede
resetear la contrasena de cualquier usuario. El admin elige la nueva
contrasena en el request.

Precondiciones:
- Solo admin puede ejecutar (require_admin en router).
- Usuario objetivo debe existir.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import bcrypt

if TYPE_CHECKING:
    from src.application.ports.auth_repository import AuthRepository
    from src.domain.entities.usuario import Usuario


class UsuarioNoEncontradoError(Exception):
    """Carnet no esta registrado."""


async def execute(
    carnet: str,
    nueva_password: str,
    auth_repo: AuthRepository,
) -> Usuario:
    """Resetea la password de un usuario a una nueva elegida por admin.

    Args:
        carnet: CI/CM del usuario objetivo.
        nueva_password: nueva contrasena en texto plano (se hashea bcrypt).
        auth_repo: AuthRepository.

    Returns:
        Usuario con password hash actualizado.

    Raises:
        UsuarioNoEncontradoError: si carnet no existe.
    """
    usuario = await auth_repo.get_by_carnet(carnet)
    if usuario is None:
        raise UsuarioNoEncontradoError

    hash_bytes = await asyncio.to_thread(
        bcrypt.hashpw, nueva_password.encode("utf-8"), bcrypt.gensalt()
    )
    nuevo_hash = hash_bytes.decode("utf-8")

    usuario.password_hash = nuevo_hash

    return await auth_repo.actualizar_usuario(usuario)
