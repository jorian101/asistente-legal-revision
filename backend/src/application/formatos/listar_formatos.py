"""Use case: ListarFormatos — lista formatos con filtros opcionales."""

from __future__ import annotations

from src.domain.entities.formato_documento import FormatoDocumento


class ListarFormatos:
    """Lista formatos filtrados por tipo/autor/estado con paginación."""

    def __init__(self, formato_repo: object) -> None:
        self._repo = formato_repo

    async def ejecutar(
        self,
        *,
        tipo_documento: str | None = None,
        autor: str | None = None,
        estado: str | None = None,
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> tuple[list[FormatoDocumento], int]:
        return await self._repo.listar(
            tipo_documento=tipo_documento,
            autor=autor,
            estado=estado,
            pagina=pagina,
            por_pagina=por_pagina,
        )


__all__ = ["ListarFormatos"]
