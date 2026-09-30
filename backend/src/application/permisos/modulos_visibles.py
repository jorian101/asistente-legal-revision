"""Use case: módulos que ve cada usuario y cada rol (tabla y alta de usuarios).

La gestión de usuarios mostraba los módulos de la matriz estática por rol del
frontend, que ignora los overrides por usuario y los módulos desactivados. Este
UC aplica la misma regla que el menú lateral (`mis_permisos`: módulos activos
con permiso de leer) a:
- cada usuario (defaults del rol ⊕ sus overrides), y
- cada rol sin overrides (lo que verá un usuario recién creado).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.permisos import mis_permisos

ROLES = ("administrador", "supervisor", "operador_juridico")


@dataclass
class ModuloVisible:
    clave: str
    nombre: str
    descripcion: str
    ruta: str


@dataclass
class ModulosVisiblesDTO:
    por_usuario: dict[str, list[ModuloVisible]]  # {carnet: módulos}
    por_rol: dict[str, list[ModuloVisible]]


async def _visibles(permiso_repo, usuario_id: int, rol: str) -> list[ModuloVisible]:
    modulos = await mis_permisos.execute(permiso_repo, usuario_id, rol)
    return [
        ModuloVisible(m.clave, m.nombre, m.descripcion, m.ruta)
        for m in modulos
        if m.efectivo.puede_leer
    ]


async def execute(permiso_repo, auth_repo) -> ModulosVisiblesDTO:
    """Resuelve los módulos visibles de todos los usuarios y de cada rol."""
    usuarios = await auth_repo.listar_usuarios()
    por_usuario = {u.carnet: await _visibles(permiso_repo, u.id or 0, u.rol) for u in usuarios}
    # usuario_id 0 no tiene overrides: son los defaults del rol.
    por_rol = {rol: await _visibles(permiso_repo, 0, rol) for rol in ROLES}
    return ModulosVisiblesDTO(por_usuario=por_usuario, por_rol=por_rol)
