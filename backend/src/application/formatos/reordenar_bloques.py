"""Use case: ReordenarBloques — reordena bloques y esqueleto según orden dado.

La clave es la lista ordenada de block_key pN:iM. Se valida que existan y
no se dupliquen. Se reordena bloques y esqueleto por el orden dado, moviendo
los no mencionados al final. No re-asigna indices para no romper pN:iM.

Se versiona el formato.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class ReordenarBloques:
    def __init__(self, formato_repo: object) -> None:
        self._repo = formato_repo

    async def ejecutar(
        self,
        formato_id: int,
        orden: list[str],
    ) -> object:
        formato = await self._repo.obtener(formato_id)
        if formato is None:
            raise ValueError(f"Formato {formato_id} no encontrado")

        def _key(b: dict[str, Any]) -> str:
            return f"p{b.get('page')}:i{b.get('index')}"

        bloques_by_key = {_key(b): b for b in formato.bloques}
        esqueleto_by_key = (
            {_key(b): b for b in (formato.esqueleto or [])} if formato.esqueleto else {}
        )

        vistos: set[str] = set()
        nuevo_bloques: list[dict[str, Any]] = []
        nuevo_esqueleto: list[dict[str, Any]] | None = [] if formato.esqueleto is not None else None

        for k in orden:
            if k in vistos:
                raise ValueError(f"Clave duplicada en orden: {k}")
            vistos.add(k)
            b = bloques_by_key.get(k)
            if b is None:
                raise ValueError(f"Bloque {k} no encontrado")
            nuevo_bloques.append(b)
            if nuevo_esqueleto is not None and esqueleto_by_key.get(k) is not None:
                nuevo_esqueleto.append(esqueleto_by_key[k])

        # Añadir restantes al final
        for k, b in bloques_by_key.items():
            if k not in vistos:
                nuevo_bloques.append(b)
        if nuevo_esqueleto is not None:
            for k, b in esqueleto_by_key.items():
                if k not in vistos:
                    nuevo_esqueleto.append(b)  # type: ignore[arg-type]

        formato.bloques = nuevo_bloques
        if nuevo_esqueleto is not None:
            formato.esqueleto = nuevo_esqueleto
        formato.version += 1
        formato.updated_at = datetime.now(UTC)
        return await self._repo.actualizar(formato)


__all__ = ["ReordenarBloques"]
