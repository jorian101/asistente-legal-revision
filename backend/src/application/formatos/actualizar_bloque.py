"""Use case: ActualizarBloque — corrige un bloque del layout y guarda.

Clave del bloque: "p<page>:i<index>" (ej. "p1:i12").
Payload parcial: texto, align, bold/italic/underline, size_pt, note, etc.
Nunca pisa layout.json a mano: esta es la única vía de edición curada.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class ActualizarBloque:
    """Corrige un bloque del formato y versiona."""

    def __init__(self, formato_repo: object) -> None:
        self._repo = formato_repo

    async def ejecutar(
        self,
        formato_id: int,
        block_key: str,
        patch: dict[str, Any],
    ) -> object:
        formato = await self._repo.obtener(formato_id)
        if formato is None:
            raise ValueError(f"Formato {formato_id} no encontrado")

        # validar clave pN:iM
        try:
            page_s, idx_s = block_key.removeprefix("p").split(":i")
            page, idx = int(page_s), int(idx_s)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"block_key inválido '{block_key}', esperado pN:iM") from exc

        bloque = next(
            (b for b in formato.bloques if b.get("page") == page and b.get("index") == idx), None
        )
        if bloque is None:
            raise ValueError(f"Bloque {block_key} no encontrado en formato {formato_id}")

        def _aplicar_patch(target: dict[str, Any]) -> None:
            if "text" in patch:
                if "texto_plantilla" in target:
                    target["texto_plantilla"] = str(patch["text"])
                if target.get("runs"):
                    target["runs"][0]["text"] = str(patch["text"])
                    target["runs"][0]["overridden"] = True
            if "align" in patch:
                target["align"] = patch["align"]
            if "bold" in patch and target.get("runs"):
                target["runs"][0]["bold"] = bool(patch["bold"])
            if "italic" in patch and target.get("runs"):
                target["runs"][0]["italic"] = bool(patch["italic"])
            if "underline" in patch and target.get("runs"):
                target["runs"][0]["underline"] = bool(patch["underline"])
            if "size_pt" in patch and target.get("runs"):
                target["runs"][0]["size_pt"] = patch["size_pt"]
            if "font" in patch and target.get("runs"):
                target["runs"][0]["font"] = patch["font"]
            if "note" in patch:
                target["note"] = patch["note"]
            target["overridden"] = True

        _aplicar_patch(bloque)

        # El preview renderiza `esqueleto` si existe; si no se parchea, la edicion
        # no se ve. Parchear tambien el bloque homologo en esqueleto (misma page:index).
        if formato.esqueleto:
            esq_bloque = next(
                (b for b in formato.esqueleto if b.get("page") == page and b.get("index") == idx),
                None,
            )
            if esq_bloque is not None:
                _aplicar_patch(esq_bloque)
        formato.version += 1
        formato.updated_at = datetime.now(UTC)

        return await self._repo.actualizar(formato)


__all__ = ["ActualizarBloque"]
