"""Recalcula el vector lexico (`text-sparse`) de los puntos ya indexados en Qdrant.

`compute_bm25_sparse` cambio (tildes, palabras vacias, normalizacion por longitud): los
vectores guardados quedan obsoletos. Se recalculan desde `payload["texto"]`, sin volver
a embeber (no usa Ollama). Idempotente. Sin `--yes` solo cuenta (dry-run).

Uso (con Qdrant levantado):
    cd backend && uv run python -m scripts.reindexar_sparse [--coleccion corpus_juridico] [--yes]
"""

from __future__ import annotations

import argparse
import sys

from qdrant_client import QdrantClient, models

from scripts._aviso import aviso_poblar  # noqa: E402
from src.application.services.hybrid_searcher import compute_bm25_sparse
from src.config import get_settings

SPARSE_VECTOR_NAME = "text-sparse"


def recalcular_sparse(
    client: QdrantClient, coleccion: str, *, aplicar: bool, lote: int = 256
) -> int:
    """Recalcula el sparse de cada punto con `payload["texto"]`. Devuelve cuantos tocaria/toco."""
    total = 0
    pendientes: list[models.PointVectors] = []
    offset = None
    while True:
        puntos, offset = client.scroll(
            collection_name=coleccion,
            limit=lote,
            offset=offset,
            with_payload=["texto"],
            with_vectors=False,
        )
        for p in puntos:
            texto = (p.payload or {}).get("texto")
            if not texto:
                continue
            total += 1
            sp = compute_bm25_sparse(texto)
            pendientes.append(
                models.PointVectors(
                    id=p.id,
                    vector={
                        SPARSE_VECTOR_NAME: models.SparseVector(
                            indices=list(sp.indices), values=list(sp.values)
                        )
                    },
                )
            )
            if aplicar and len(pendientes) >= lote:
                client.update_vectors(collection_name=coleccion, points=pendientes)
                pendientes = []
        if offset is None:
            break
    if aplicar and pendientes:
        client.update_vectors(collection_name=coleccion, points=pendientes)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Recalcula el sparse de una coleccion Qdrant")
    parser.add_argument("--coleccion", default="corpus_juridico")
    parser.add_argument("--yes", action="store_true", help="aplicar (sin esto solo cuenta)")
    args = parser.parse_args()

    settings = get_settings()
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    n = recalcular_sparse(client, args.coleccion, aplicar=args.yes)
    print(f"{'Recalculados' if args.yes else 'Recalcularia'} {n} puntos de '{args.coleccion}'.")
    if not args.yes:
        print("Dry-run: repetir con --yes para aplicar.")
    aviso_poblar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
