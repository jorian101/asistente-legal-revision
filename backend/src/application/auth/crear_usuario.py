"""Use case: Crear usuario (admin only, HU-01).

Sprint 1 Auth (plan v3). Admin registra un usuario con rol, cargo y carnet.

Precondiciones:
- Solo admin puede ejecutar (validado por dependency require_admin en router).
- Carnet debe ser unico (validado por unique index ix_usuario_carnet en BD).
"""

from __future__ import annotations

import asyncio
from typing import cast

import bcrypt

from src.domain.entities.usuario import (
    RolUsuario,
    Usuario,
    validar_cargo_para_rol,
)


class CarnetDuplicadoError(Exception):
    """El carnet ya esta registrado (unique constraint)."""


async def execute(
    nombre: str,
    carnet: str,
    password: str,
    rol: str,
    cargo: str,
    auth_repo,
    email: str | None = None,
) -> Usuario:
    """Crea un usuario nuevo con password hasheada.

    Args:
        nombre: nombre completo del usuario.
        carnet: CI/CM alfanumerico (unique).
        password: contrasena en texto plano del nuevo usuario.
        rol: perfil de acceso (administrador/supervisor/operador_juridico).
        cargo: rol institucional real (Tabla 12: Auditor/Fiscal/Vocal/...).
        auth_repo: AuthRepository.
        email: email opcional para 2FA (Fase 2).

    Returns:
        Usuario creado con id asignado y password hasheado.

    Raises:
        CarnetDuplicadoError: si carnet ya existe.
        CargoInvalidoParaRolError: si el cargo no corresponde al rol (Tabla 12).
    """
    validar_cargo_para_rol(rol, cargo)

    hash_bytes = await asyncio.to_thread(bcrypt.hashpw, password.encode("utf-8"), bcrypt.gensalt())
    password_hash = hash_bytes.decode("utf-8")

    usuario = Usuario(
        id=None,
        nombre=nombre,
        carnet=carnet,
        password_hash=password_hash,
        rol=cast(RolUsuario, rol),
        cargo=cargo,
        activo=True,
        email=email.strip() if email else None,
        email_verificado=False,
    )

    return await auth_repo.crear_usuario(usuario)
