"""Use case: Modificar usuario (admin only, HU-02).

Sprint 1 Auth (plan v3). Admin modifica rol o estado (activo/inactivo) de un usuario existente.

Precondiciones:
- Solo admin puede ejecutar (validado por require_admin en router).
- Usuario objetivo debe existir.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.entities.usuario import validar_cargo_para_rol

if TYPE_CHECKING:
    from src.application.ports.auth_repository import AuthRepository
    from src.domain.entities.usuario import RolUsuario, Usuario


class UsuarioNoEncontradoError(Exception):
    """Carnet no esta registrado."""


async def execute(
    carnet: str,
    auth_repo: AuthRepository,
    *,
    rol: RolUsuario | None = None,
    cargo: str | None = None,
    activo: bool | None = None,
    email: str | None = None,
    nombre: str | None = None,
    carnet_nuevo: str | None = None,
) -> Usuario:
    """Actualiza rol/cargo/activo/email/nombre/carnet de usuario por carnet.

    Args:
        carnet: CI/CM del usuario a modificar (identificador actual).
        auth_repo: AuthRepository.
        rol: nuevo rol (None = no modificar).
        cargo: nuevo cargo (None = no modificar).
        activo: nuevo estado (None = no modificar).
        email: nuevo email (None = no modificar). Al cambiar el email,
            email_verificado vuelve a False (requiere re-verificacion 2FA).
        nombre: nuevo nombre completo (None = no modificar).
        carnet_nuevo: nuevo CI/CM de inicio de sesion (None = no modificar).

    Returns:
        Usuario actualizado.

    Raises:
        UsuarioNoEncontradoError: si carnet no existe.
        CargoInvalidoParaRolError: si el par (rol, cargo) resultante no es
            valido segun Tabla 12 (rol nuevo con cargo existente, o cargo
            nuevo para el rol actual).
        CarnetDuplicadoError: si carnet_nuevo ya esta registrado.
    """
    usuario = await auth_repo.get_by_carnet(carnet)
    if usuario is None:
        raise UsuarioNoEncontradoError

    rol_nuevo = rol if rol is not None else usuario.rol
    cargo_nuevo = cargo if cargo is not None else usuario.cargo
    validar_cargo_para_rol(rol_nuevo, cargo_nuevo)

    if rol is not None:
        usuario.rol = rol
    if cargo is not None:
        usuario.cargo = cargo
    if activo is not None:
        usuario.activo = activo
    if email is not None and email.strip() != "":
        usuario.email = email.strip()
        usuario.email_verificado = False
    if nombre is not None and nombre.strip() != "":
        usuario.nombre = nombre.strip()
    if carnet_nuevo is not None and carnet_nuevo.strip() != "":
        usuario.carnet = carnet_nuevo.strip()

    return await auth_repo.actualizar_usuario(usuario, carnet_original=carnet)
