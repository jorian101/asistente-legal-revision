"""Use case: actualizar el perfil propio sin tocar permisos institucionales."""

from __future__ import annotations

import asyncio

import bcrypt

from src.application.ports.auth_repository import AuthRepository


class PerfilError(ValueError):
    """La actualización del perfil no cumple las reglas de seguridad."""


async def execute(
    *,
    auth_repo: AuthRepository,
    usuario_id: int,
    nombre: str,
    email: str | None,
    password_actual: str | None,
    password_nueva: str | None,
):
    """Actualiza nombre/email/password del propio usuario.

    Args:
        email: nuevo email (None = no modificar). Al cambiarlo,
            email_verificado vuelve a False (requiere re-verificacion 2FA).
        password_nueva: nueva contraseña (None = no modificar; si viene,
            password_actual es obligatorio y se valida).
    """
    usuario = await auth_repo.get_by_id(usuario_id)
    if usuario is None or not usuario.activo:
        raise PerfilError("Usuario no encontrado.")

    if password_nueva is not None:
        if password_actual is None or not await asyncio.to_thread(
            bcrypt.checkpw,
            password_actual.encode("utf-8"),
            usuario.password_hash.encode("utf-8"),
        ):
            raise PerfilError("La contraseña actual no es válida.")
        if len(password_nueva) < 6:
            raise PerfilError("La nueva contraseña debe tener al menos 6 caracteres.")
        hash_bytes = await asyncio.to_thread(
            bcrypt.hashpw, password_nueva.encode("utf-8"), bcrypt.gensalt()
        )
        usuario.password_hash = hash_bytes.decode("utf-8")

    usuario.nombre = nombre.strip()
    if not usuario.nombre:
        raise PerfilError("El nombre es obligatorio.")
    if email is not None and email.strip() != "":
        email_limpio = email.strip()
        if email_limpio != usuario.email:
            usuario.email = email_limpio
            usuario.email_verificado = False

    return await auth_repo.actualizar_usuario(usuario)
