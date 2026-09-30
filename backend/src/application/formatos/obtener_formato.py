"""Use case: ObtenerFormato — obtiene un formato por id o slug."""

from __future__ import annotations

from src.domain.entities.formato_documento import FormatoDocumento


class ObtenerFormato:
    """Obtiene un formato por id o slug."""

    def __init__(self, formato_repo: object) -> None:
        self._repo = formato_repo

    async def ejecutar_por_id(self, formato_id: int) -> FormatoDocumento:
        formato = await self._repo.obtener(formato_id)
        if formato is None:
            raise ValueError(f"Formato {formato_id} no encontrado")
        return formato

    async def ejecutar_por_slug(self, slug: str) -> FormatoDocumento:
        formato = await self._repo.obtener_por_slug(slug)
        if formato is None:
            raise ValueError(f"Formato slug '{slug}' no encontrado")
        return formato


__all__ = ["ObtenerFormato"]
