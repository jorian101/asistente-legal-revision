"""Port: NormaRepo — Repositorio de normas (tabla `norma`).

Protocols (structural typing) — las implementaciones no necesitan heredar.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.norma import Norma


class NormaRepo(Protocol):
    """Repositorio de normas (tabla `norma`)."""

    async def save(self, norma: Norma) -> Norma:
        """Inserta o actualiza una norma. Devuelve norma con ID asignado."""
        ...

    async def get_by_id(self, norma_id: int) -> Norma | None:
        """Obtiene Norma por PK."""
        ...

    async def actualizar(
        self,
        norma_id: int,
        *,
        nombre: str | None = None,
        version: str | None = None,
    ) -> Norma | None:
        """Actualiza metadatos (nombre, versión) de una norma."""
        ...

    async def get_by_abreviatura(self, abreviatura: str) -> Norma | None:
        """Obtiene norma por abreviatura unica (UNIQUE constraint)."""
        ...

    async def list_all(self) -> list[Norma]:
        """Lista todas las normas ordenadas por abreviatura."""
        ...

    async def marcar_indexada(self, norma_id: int, indexado_por: int | None) -> None:
        """Marca norma como indexada (indexado=True, indexado_por=usuario)."""
        ...

    async def actualizar_visibilidad(
        self, norma_id: int, estado: str, motivo_rechazo: str | None = None
    ) -> Norma | None:
        """Cambia estado_visibilidad (privado|pendiente|global|rechazado)."""
        ...

    async def eliminar_soft(self, norma_id: int) -> bool:
        """Soft delete: activo=False (CRITICAL #3). True si existia y activa."""
        ...
