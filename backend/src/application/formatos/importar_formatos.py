"""Use case: ImportarFormatos — importa layouts del pipeline vault → PG.

Lee `vault/sources/formatos/**/layout.json` (ruta configurable), hace
upsert por `hash_fuente`/`slug`. Respeta `canonico` (no pisa).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.domain.entities.formato_documento import FormatoDocumento


class ImportarFormatos:
    """Importa layouts del pipeline a la tabla formato_documento."""

    def __init__(self, formato_repo: object) -> None:
        self._repo = formato_repo

    async def ejecutar(self, vault_root: Path) -> dict[str, int]:
        vault_root = Path(vault_root)
        layouts = sorted(vault_root.rglob("layout.json"))
        importados = 0
        omitidos = 0
        for layout_path in layouts:
            try:
                data = json.loads(layout_path.read_text(encoding="utf-8"))
            except Exception:
                omitidos += 1
                continue
            meta = data.get("meta", {})
            bloques = data.get("blocks", [])
            # leer el formato.json hermano (esqueleto con template/texto_plantilla/placeholders)
            esqueleto = None
            formato_path = layout_path.parent / "formato.json"
            if formato_path.exists():
                try:
                    esqueleto = json.loads(formato_path.read_text(encoding="utf-8")).get(
                        "esqueleto"
                    )
                except Exception:
                    esqueleto = None
            # derivar tipo/autor del path: vault/sources/formatos/<tipo>/<slug>/layout.json
            try:
                tipo = layout_path.parent.parent.name
                slug = layout_path.parent.name
            except Exception:
                omitidos += 1
                continue
            # autor y tipo del manifiesto o meta; fallback a path
            tipo_doc = meta.get("tipo") or tipo
            autor = meta.get("autor") or "desconocido"
            engine = meta.get("engine") or "desconocido"
            hash_fuente = (
                meta.get("hash_fuente") or hashlib.sha256(layout_path.read_bytes()).hexdigest()[:16]
            )

            existente = await self._repo.obtener_por_slug(slug)
            if existente is not None:
                if existente.estado == "canonico":
                    omitidos += 1
                    continue
                if existente.hash_fuente == hash_fuente:
                    # Rellenar esqueleto si el registro previo no lo traía
                    # (importado antes de la columna esqueleto).
                    if not existente.esqueleto and esqueleto:
                        existente.esqueleto = esqueleto
                        existente.version += 1
                        await self._repo.actualizar(existente)
                        importados += 1
                    else:
                        omitidos += 1
                    continue
                # actualizar borrador existente
                existente.tipo_documento = tipo_doc  # type: ignore[assignment]
                existente.autor = autor  # type: ignore[assignment]
                existente.engine = engine
                existente.meta = meta
                existente.bloques = bloques
                existente.esqueleto = esqueleto
                existente.hash_fuente = hash_fuente
                existente.version += 1
                await self._repo.actualizar(existente)
                importados += 1
                continue

            nuevo = FormatoDocumento(
                id=None,
                tipo_documento=tipo_doc,  # type: ignore[arg-type]
                slug=slug,
                autor=autor,  # type: ignore[arg-type]
                engine=engine,
                meta=meta,
                bloques=bloques,
                esqueleto=esqueleto,
                estado="borrador",
                version=1,
                hash_fuente=hash_fuente,
            )
            await self._repo.guardar(nuevo)
            importados += 1

        return {"importados": importados, "omitidos": omitidos, "total": len(layouts)}
