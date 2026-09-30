"""Use case: PromoverFormato — marca un formato como canónico del tipo.

Regla: solo un canonico por tipo_documento. Al promover uno, los demás
del mismo tipo vuelven a borrador.
"""

from __future__ import annotations

from datetime import UTC, datetime


class PromoverFormato:
    """Promueve un formato a canonico (semilla del tipo)."""

    def __init__(self, formato_repo: object) -> None:
        self._repo = formato_repo

    async def ejecutar(self, formato_id: int) -> object:
        formato = await self._repo.obtener(formato_id)
        if formato is None:
            raise ValueError(f"Formato {formato_id} no encontrado")

        # despromover otros canonicos del mismo tipo
        existentes, _ = await self._repo.listar(
            tipo_documento=formato.tipo_documento, estado="canonico", pagina=1, por_pagina=100
        )
        for otro in existentes:
            if otro.id != formato.id:
                otro.estado = "borrador"  # type: ignore[assignment]
                otro.version += 1
                otro.updated_at = datetime.now(UTC)
                await self._repo.actualizar(otro)

        formato.estado = "canonico"  # type: ignore[assignment]
        formato.version += 1
        formato.updated_at = datetime.now(UTC)
        return await self._repo.actualizar(formato)


__all__ = ["PromoverFormato"]
