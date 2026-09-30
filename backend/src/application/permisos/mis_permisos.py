"""Use case: Permisos EFECTIVOS de los módulos visibles para el usuario logueado.

Para el sidebar dinámico del frontend (Fase 2 del plan
`plan/permisos-crud-modulos`): el usuario autenticado necesita saber qué
módulos del catálogo (activos) puede ver y con qué operaciones, sin tener que
inferir la matriz del rol.

Devuelve los módulos activos con su permiso efectivo (defaults rol ⊕
overrides). El admin siempre ve el catálogo completo con full.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.entities.permiso import PermisoEfectivo


@dataclass
class ModuloPermisoDTO:
    clave: str
    nombre: str
    descripcion: str
    ruta: str
    orden: int
    efectivo: PermisoEfectivo


async def execute(permiso_repo, usuario_id: int, rol: str) -> list[ModuloPermisoDTO]:
    """Lista módulos activos con permisos efectivos del usuario.

    Args:
        permiso_repo: PermisoRepo.
        usuario_id: id del usuario logueado.
        rol: rol del usuario (define los defaults).

    Returns:
        Módulos activos del catálogo (ordenados), con su permiso efectivo.
    """
    from src.application.permisos import resolver_permisos_usuario

    modulos = await permiso_repo.listar_modulos()
    efectivos = await resolver_permisos_usuario.execute(permiso_repo, usuario_id, rol)

    dto: list[ModuloPermisoDTO] = []
    for modulo in modulos:
        if not modulo.activo:
            continue
        efectivo = efectivos.get(modulo.clave)
        if efectivo is None:
            continue
        dto.append(
            ModuloPermisoDTO(
                clave=modulo.clave,
                nombre=modulo.nombre,
                descripcion=modulo.descripcion,
                ruta=modulo.ruta,
                orden=modulo.orden,
                efectivo=efectivo,
            )
        )
    return dto
