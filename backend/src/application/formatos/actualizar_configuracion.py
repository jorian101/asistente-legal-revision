"""Use case: ActualizarConfiguracionFormato — persiste config global de página/fuente.

Ajusta `meta.page` (tamaño de hoja + márgenes) y `meta.base` (fuente/tamaño de
fuente globales) del formato, para que el export .docx respete lo que el
usuario vio en el preview. Merge parcial: no pisa claves no enviadas.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class ActualizarConfiguracionFormato:
    def __init__(self, formato_repo: object) -> None:
        self._repo = formato_repo

    async def ejecutar(
        self,
        formato_id: int,
        *,
        page: dict[str, Any] | None = None,
        base: dict[str, Any] | None = None,
    ) -> object:
        formato = await self._repo.obtener(formato_id)
        if formato is None:
            raise ValueError(f"Formato {formato_id} no encontrado")

        meta = dict(formato.meta or {})
        if page:
            meta["page"] = {**(meta.get("page") or {}), **page}
        if base:
            meta["base"] = {**(meta.get("base") or {}), **base}
        formato.meta = meta
        formato.version += 1
        formato.updated_at = datetime.now(UTC)
        return await self._repo.actualizar(formato)


__all__ = ["ActualizarConfiguracionFormato"]
