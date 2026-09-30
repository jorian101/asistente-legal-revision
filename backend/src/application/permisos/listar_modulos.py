"""Use case: Listar módulos del catálogo (admin).

Decision `plan/permisos-crud-modulos`: el catálogo de módulos es FIJO
(sembrado por migración con los 11 módulos actuales). Este UC devuelve la
lista completa para que el admin los active/desactive y asigne permisos.
"""

from __future__ import annotations

from src.domain.entities.permiso import Modulo


async def execute(permiso_repo) -> list[Modulo]:
    """Lista todos los módulos ordenados por `orden`."""
    return await permiso_repo.listar_modulos()
