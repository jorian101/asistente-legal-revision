"""Port: FormatoRepo — Repositorio de formatos de obrados TSJM.

Protocols (structural typing).
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.formato_documento import FormatoDocumento


class FormatoRepo(Protocol):
    """Repositorio de formatos (tabla `formato_documento`)."""

    async def guardar(self, formato: FormatoDocumento) -> FormatoDocumento:
        """Crea un formato. Devuelve entidad con id asignado."""
        ...

    async def obtener(self, formato_id: int) -> FormatoDocumento | None:
        """Obtiene por PK."""
        ...

    async def obtener_por_slug(self, slug: str) -> FormatoDocumento | None:
        """Obtiene por UNIQUE slug."""
        ...

    async def listar(
        self,
        *,
        tipo_documento: str | None = None,
        autor: str | None = None,
        estado: str | None = None,
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> tuple[list[FormatoDocumento], int]:
        """Lista formatos con filtros opcionales + paginación."""
        ...

    async def actualizar(self, formato: FormatoDocumento) -> FormatoDocumento:
        """Persiste cambios de una entidad existente (bloques, meta, estado...)."""
        ...

    async def eliminar(self, formato_id: int) -> bool:
        """Elimina por PK. True si existía."""
        ...
