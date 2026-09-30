"""Script de verificacion: coleccion `corpus_juridico` en Qdrant.

Verifica que la coleccion exista y reporta su configuracion actual:
- existencia de la coleccion
- dimension del vector denso (debe coincidir con EMBEDDING_DIM de .env)
- distancia configurada
- si tiene sparse vectors configurados (requerido para BM25 server-side,
  Sprint 3 / decision D1 del plan)

Uso:
    uv run python scripts/verify_collection_schema.py

Exit code:
    0 = coleccion OK (sparse presente o ausente, solo informativo)
    2 = coleccion no existe o error de conexion
"""

from __future__ import annotations

import sys
from pathlib import Path

from qdrant_client import QdrantClient

# Asegurar que el directorio backend/ esté en el path para importar 'src'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_settings  # noqa: E402

COLLECTION = "corpus_juridico"


def main() -> int:
    settings = get_settings()
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

    collections = {c.name for c in client.get_collections().collections}
    if COLLECTION not in collections:
        print(f"[FALLO] Coleccion '{COLLECTION}' no existe en Qdrant.")
        return 2

    info = client.get_collection(COLLECTION)
    params = info.config.params
    vectors = params.vectors

    print(f"[OK] Coleccion '{COLLECTION}' existe.")
    print(f"  - puntos: {info.points_count}")
    if hasattr(vectors, "size"):
        dense_size = vectors.size
        dense_distance = str(vectors.distance)
    else:
        dense_size = None
        dense_distance = "n/a (multiple named vectors)"

    print(f"  - vector denso size={dense_size} distance={dense_distance}")

    sparse = getattr(params, "sparse_vectors", None)
    if sparse:
        print(f"  - sparse vectors configurados: {list(sparse.keys())}")
    else:
        print("  - sparse vectors: NO configurados (BM25 server-side inactivo)")

    if dense_size is not None and dense_size != settings.embedding_dim:
        print(
            f"[WARN] Dimension {dense_size} != EMBEDDING_DIM "
            f"({settings.embedding_dim}). Los vectores no matchean."
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
