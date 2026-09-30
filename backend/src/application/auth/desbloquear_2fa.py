"""Use case: Desbloquear 2FA de un usuario (admin only).

Fase 2 plan jurado. Cuando un usuario acumula 3 intentos de codigo 2FA
invalido, queda bloqueado (bloqueado_hasta = now+1h). Solo admin puede
desbloquear (coincide con la Regla 2 Trail of Bits: "solo Admin desbloquea").

Precondiciones:
- Solo admin puede ejecutar (validado por require_admin en router).
- Usuario objetivo debe existir.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports.auth_repository import AuthRepository


class UsuarioNoEncontradoError(Exception):
    """Carnet no esta registrado."""


async def execute(carnet: str, auth_repo: AuthRepository) -> None:
    """Desbloquea la cuenta 2FA de un usuario.

    Args:
        carnet: CI/CM del usuario a desbloquear.
        auth_repo: AuthRepository.

    Raises:
        UsuarioNoEncontradoError: si carnet no existe.
    """
    usuario = await auth_repo.get_by_carnet(carnet)
    if usuario is None:
        raise UsuarioNoEncontradoError

    await auth_repo.desbloquear_2fa(carnet)
