"""Use case: Resolver permisos EFECTIVOS de un usuario (defaults rol ⊕ overrides).

Este UC es el que usa el guard `require_permiso` en cada request: dados el
usuario y su rol, devuelve los permisos CRUD efectivos por módulo, sin
confiar en el JWT ni en el frontend (Regla 2 Trail of Bits: re-validar contra
BD).

El rol administrador se resuelve con defaults_para_rol("administrador"): full
en todos los módulos de GESTIÓN (y full automático para módulos admin nuevos),
pero SIN acceso a los módulos de consulta (espeja require_consulta_user). Sus
overrides nunca se aplican (asignar_permisos_usuario bloquea modificar admin).

Un módulo desactivado en el catálogo queda denegado para supervisor y
operador (el guard responde 403, no solo desaparece del menú). El admin
conserva su acceso de gestión para poder reactivarlo.
"""

from __future__ import annotations

from src.domain.entities.permiso import (
    PermisoCRUD,
    PermisoEfectivo,
    defaults_para_rol,
)


async def execute(permiso_repo, usuario_id: int, rol: str) -> dict[str, PermisoEfectivo]:
    """Resuelve los permisos efectivos del usuario por módulo.

    Returns:
        {clave_modulo: PermisoEfectivo}: defaults del rol combinados con los
        overrides del usuario (el admin nunca tiene overrides).
    """
    modulos = await permiso_repo.listar_modulos()
    overrides = await permiso_repo.get_permisos_usuario(usuario_id)
    defaults = defaults_para_rol(rol)

    # Regla de seguridad: el admin nunca se degrada por overrides. Aunque
    # asignar_permisos_usuario bloquea modificar admin, un override que llegue
    # por otra vía no debe reducir su acceso a los módulos de gestión.
    if rol == "administrador":
        overrides = {}

    efectivos: dict[str, PermisoEfectivo] = {}
    for modulo in modulos:
        if not modulo.activo and rol != "administrador":
            efectivos[modulo.clave] = PermisoEfectivo(False, False, False, False)
            continue
        override = overrides.get(modulo.clave, PermisoCRUD())
        default = defaults.get(modulo.clave, PermisoCRUD(False, False, False, False))
        resuelto = override.resolver(default)
        efectivos[modulo.clave] = PermisoEfectivo(
            puede_crear=bool(resuelto.puede_crear),
            puede_leer=bool(resuelto.puede_leer),
            puede_actualizar=bool(resuelto.puede_actualizar),
            puede_eliminar=bool(resuelto.puede_eliminar),
        )
    return efectivos
