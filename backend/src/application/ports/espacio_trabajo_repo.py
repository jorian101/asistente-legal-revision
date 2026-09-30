"""Port: EspacioTrabajoRepo — Repositorio de carpetas de chat (tabla `espacio_trabajo`).

Protocols (structural typing) — las implementaciones no necesitan heredar.

Sprint 4 (Opción B #133): carpetas del sidebar (fijado/archivado/personalizado)
reemplazan FolderItem del chatStore localStorage.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.espacio_trabajo import EspacioTrabajo


class EspacioTrabajoRepo(Protocol):
    """Repositorio de carpetas de chat (tabla `espacio_trabajo`)."""

    async def guardar(self, espacio: EspacioTrabajo) -> EspacioTrabajo:
        """Crea una carpeta. Devuelve entidad con id asignado."""
        ...

    async def obtener(self, espacio_id: int, propietario_id: int) -> EspacioTrabajo | None:
        """Obtiene una carpeta por id, filtrando por propietario (Regla 5)."""
        ...

    async def listar_por_expediente(
        self,
        expediente_id: int,
        propietario_id: int,
        estado: str | None = "activo",
    ) -> list[EspacioTrabajo]:
        """Lista carpetas del usuario dentro de un expediente."""
        ...

    async def cambiar_tipo(
        self, espacio_id: int, propietario_id: int, tipo: str
    ) -> EspacioTrabajo | None:
        """Cambia el tipo (fijado/archivado/personalizado). Devuelve actualizado."""
        ...
