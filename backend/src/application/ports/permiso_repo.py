"""Port: PermisoRepo — Repositorio de módulos y permisos CRUD por usuario.

Decision `plan/permisos-crud-modulos`. Protocol — structural typing, las
implementaciones no necesitan heredar. La implementacion SqlPermisoRepo vive
en adapters/postgres/ y conoce SQLAlchemy. Los use cases solo dependen de
este protocolo.

Responsabilidades:
- `modulo`: listar el catálogo (fijo), actualizar metadata (nombre/descripcion/
  ruta/orden/activo). El catálogo se siembra por migración, no se crea/borra.
- `usuario_modulo_permiso`: guardar/borrar overrides de permisos CRUD por
  usuario, y listar los overrides de un usuario (o de todos).
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.permiso import Modulo, PermisoCRUD


class PermisoRepo(Protocol):
    """Repositorio de módulos y permisos. Implementado por SqlPermisoRepo."""

    # --- módulos ---

    async def listar_modulos(self) -> list[Modulo]:
        """Lista todos los módulos del catálogo ordenados por `orden`."""
        ...

    async def actualizar_modulo(self, clave: str, **campos) -> Modulo:
        """Actualiza metadata de un módulo (nombre/descripcion/ruta/orden/activo).

        Raises:
            KeyError: si la clave no existe.
        """
        ...

    # --- overrides de usuario ---

    async def get_permisos_usuario(self, usuario_id: int) -> dict[str, PermisoCRUD]:
        """Overrides del usuario: {clave_modulo: PermisoCRUD}. Solo módulos con override."""
        ...

    async def reemplazar_permisos_usuario(
        self, usuario_id: int, permisos: dict[str, PermisoCRUD]
    ) -> None:
        """Reemplaza todos los overrides del usuario (transaccional).

        Los módulos presentes en `permisos` se upsertean; los que no están
        y tenían override se eliminan. Un PermisoCRUD con todos los flags
        None equivale a "quitar override" (seguir default del rol).
        """
        ...
