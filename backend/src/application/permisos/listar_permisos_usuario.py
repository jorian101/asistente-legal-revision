"""Use case: Listar permisos de un usuario sobre los módulos (admin).

Devuelve, por cada módulo del catálogo, el override del usuario (nullable) y
el permiso EFECTIVO (default del rol ⊕ override). El admin ve qué overrides
hay asignados y qué acceso efectivo tiene el usuario sin necesidad de inferir
la matriz del rol manualmente.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.entities.permiso import (
    PermisoCRUD,
    PermisoEfectivo,
    defaults_para_rol,
)


@dataclass
class PermisoModuloDetalle:
    clave: str
    nombre: str
    override: PermisoCRUD  # flags None = sin override
    efectivo: PermisoEfectivo
    default_rol: PermisoEfectivo  # lo que da el rol sin override


async def execute(permiso_repo, auth_repo, usuario_id: int, rol: str) -> list[PermisoModuloDetalle]:
    """Lista permisos (override + efectivo) del usuario por módulo.

    Args:
        permiso_repo: PermisoRepo.
        auth_repo: AuthRepository (para validar que el usuario exista).
        usuario_id: id del usuario a consultar.
        rol: rol del usuario (define los defaults).
    """
    if await auth_repo.get_by_id(usuario_id) is None:
        raise ValueError("Usuario no encontrado")

    modulos = await permiso_repo.listar_modulos()
    overrides = await permiso_repo.get_permisos_usuario(usuario_id)
    defaults = defaults_para_rol(rol)

    detalle: list[PermisoModuloDetalle] = []
    for modulo in modulos:
        override = overrides.get(modulo.clave, PermisoCRUD())
        default = defaults.get(modulo.clave, PermisoCRUD(False, False, False, False))
        resuelto = override.resolver(default)
        detalle.append(
            PermisoModuloDetalle(
                clave=modulo.clave,
                nombre=modulo.nombre,
                override=override,
                efectivo=PermisoEfectivo(
                    puede_crear=bool(resuelto.puede_crear),
                    puede_leer=bool(resuelto.puede_leer),
                    puede_actualizar=bool(resuelto.puede_actualizar),
                    puede_eliminar=bool(resuelto.puede_eliminar),
                ),
                default_rol=PermisoEfectivo(
                    puede_crear=bool(default.puede_crear),
                    puede_leer=bool(default.puede_leer),
                    puede_actualizar=bool(default.puede_actualizar),
                    puede_eliminar=bool(default.puede_eliminar),
                ),
            )
        )
    return detalle
