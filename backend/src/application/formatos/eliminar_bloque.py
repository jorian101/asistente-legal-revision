"""Use case: EliminarBloque — elimina un bloque del formato (bloques y esqueleto)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class EliminarBloque:
    def __init__(self, formato_repo: object) -> None:
        self._repo = formato_repo

    async def ejecutar(self, formato_id: int, block_key: str) -> object:
        formato = await self._repo.obtener(formato_id)
        if formato is None:
            raise ValueError(f"Formato {formato_id} no encontrado")

        try:
            page_s, idx_s = block_key.removeprefix("p").split(":i")
            page, idx = int(page_s), int(idx_s)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"block_key inválido '{block_key}'") from exc

        def _match(b: dict[str, Any]) -> bool:
            return b.get("page") == page and b.get("index") == idx

        bloques_antes = len(formato.bloques)
        formato.bloques = [b for b in formato.bloques if not _match(b)]
        if len(formato.bloques) == bloques_antes:
            raise ValueError(f"Bloque {block_key} no encontrado")

        if formato.esqueleto is not None:
            formato.esqueleto = [b for b in formato.esqueleto if not _match(b)]

        formato.version += 1
        formato.updated_at = datetime.now(UTC)
        return await self._repo.actualizar(formato)


__all__ = ["EliminarBloque"]
