"""Use case: Actualizar metadata de un módulo (admin).

Permite al admin editar nombre/descripcion/ruta/orden/activo de un módulo
del catálogo fijo. No permite crear ni eliminar módulos (catálogo fijo —
decision `plan/permisos-crud-modulos`).
"""

from __future__ import annotations

from src.domain.entities.permiso import Modulo


class ModuloNoEncontradoError(Exception):
    """La clave del módulo no existe en el catálogo."""


async def execute(permiso_repo, clave: str, **campos) -> Modulo:
    """Actualiza la metadata de un módulo. Devuelve el módulo actualizado.

    Raises:
        ModuloNoEncontradoError: si la clave no existe.
    """
    try:
        return await permiso_repo.actualizar_modulo(clave, **campos)
    except KeyError:
        raise ModuloNoEncontradoError(clave) from None
