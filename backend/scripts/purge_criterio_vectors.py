"""Purga idempotente de vectores 'criterio' en Qdrant.

Los criterios del Vocal se inyectan al prompt via {{criterio_vocal}}, no son
fuente RAG. Un reindex anterior (reindex_embeddings.py) los col6 en la
coleccion corpus_juridico con tipo_documento=criterio. Este script los borra.
No toca normas ni obras reales. Correr: (cd backend && uv run python -m
scripts.purge_criterio_vectors)
"""

from __future__ import annotations

from qdrant_client import QdrantClient, models

from src.config import get_settings


def main() -> int:
    client = QdrantClient(url=get_settings().qdrant_url, api_key=get_settings().qdrant_api_key)
    filtro = models.Filter(
        must=[
            models.FieldCondition(key="tipo_documento", match=models.MatchValue(value="criterio"))
        ]
    )
    ids: list[str] = []
    offset = None
    while True:
        records, offset = client.scroll(
            collection_name="corpus_juridico",
            scroll_filter=filtro,
            limit=256,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        ids.extend(str(r.id) for r in records)
        if offset is None:
            break
    if not ids:
        print("Sin vectores criterio. Nada que purgar.")
        return 0
    for i in range(0, len(ids), 256):
        client.delete(
            collection_name="corpus_juridico",
            points_selector=models.PointIdsList(points=ids[i : i + 256]),
            wait=True,
        )
    print(f"Purgados {len(ids)} vectores criterio de corpus_juridico.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
