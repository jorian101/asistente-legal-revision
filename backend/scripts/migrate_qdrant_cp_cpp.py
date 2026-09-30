"""Migra payload abreviatura LEY1970_CP/CPP -> CP/CPP en Qdrant.

Uso: (cd backend && uv run python -m scripts.migrate_qdrant_cp_cpp)
Idempotente: si no hay puntos viejos, no hace nada.
"""

from __future__ import annotations

from qdrant_client import QdrantClient, models

from src.config import get_settings

MAPEO = {"LEY1970_CP": "CP", "LEY1970_CPP": "CPP"}


def main() -> int:
    client = QdrantClient(url=get_settings().qdrant_url, api_key=get_settings().qdrant_api_key)
    for viejo, nuevo in MAPEO.items():
        # Scroll por abreviatura vieja
        offset = None
        ids_por_actualizar: list[str] = []
        # También detectar padre_ref_key con prefijo viejo para migrarlo
        while True:
            records, offset = client.scroll(
                collection_name="corpus_juridico",
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="abreviatura", match=models.MatchValue(value=viejo)
                        )
                    ]
                ),
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for r in records:
                ids_por_actualizar.append(str(r.id))
                # Preparar payloads para set_payload
            if offset is None:
                break
        if not ids_por_actualizar:
            print(f"Sin puntos con abreviatura={viejo}")
            continue
        print(f"Migrando {len(ids_por_actualizar)} puntos {viejo} -> {nuevo}")
        # Batch set_payload
        for i in range(0, len(ids_por_actualizar), 256):
            batch = ids_por_actualizar[i : i + 256]
            client.set_payload(
                collection_name="corpus_juridico",
                payload={"abreviatura": nuevo},
                points=batch,
            )
        # Migrar padre_ref_key con prefijo viejo (ej. LEY1970 -> CP)
        # No hay filtro por prefijo, se re-scrollea y actualiza
        offset = None
        while True:
            records, offset = client.scroll(
                collection_name="corpus_juridico",
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="abreviatura", match=models.MatchValue(value=nuevo)
                        )
                    ]
                ),
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            # Filtrar los que aún tienen padre_ref_key viejo
            to_fix = []
            for r in records:
                prk = (r.payload or {}).get("padre_ref_key")
                if prk and prk.startswith(viejo):
                    to_fix.append((str(r.id), prk))
            for pid, old_key in to_fix:
                new_key = old_key.replace(viejo, nuevo, 1)
                client.set_payload(
                    collection_name="corpus_juridico",
                    payload={"padre_ref_key": new_key},
                    points=[pid],
                )
            if offset is None:
                break
        print("  padre_ref_key migrados donde aplicaba")
    print("Migración Qdrant CP/CPP completada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
