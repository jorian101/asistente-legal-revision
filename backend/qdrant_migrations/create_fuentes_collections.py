#!/usr/bin/env python3
"""Migracion Qdrant: crea las colecciones `jurisprudencia` y `doctrina`.

Hasta ahora solo se creaban de forma perezosa al indexar la primera sentencia o
libro; una busqueda antes de eso las encontraba inexistentes. Idempotente: las que
ya existen no se tocan (la dimension se valida al indexar, como en corpus_juridico).
Ejecutar: `uv run python qdrant_migrations/create_fuentes_collections.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qdrant_client import QdrantClient  # noqa: E402

from src.adapters.qdrant.qdrant_doctrina_repo import QdrantDoctrinaRepo  # noqa: E402
from src.adapters.qdrant.qdrant_jurisprudencia_repo import QdrantJurisprudenciaRepo  # noqa: E402
from src.config import get_settings  # noqa: E402

_REPOS = (QdrantJurisprudenciaRepo, QdrantDoctrinaRepo)


def crear_colecciones(client: QdrantClient, dim: int) -> list[str]:
    """Crea las colecciones que falten con el esquema completo del adapter."""
    existentes = {c.name for c in client.get_collections().collections}
    creadas: list[str] = []
    for repo_cls in _REPOS:
        if repo_cls.COLLECTION_NAME in existentes:
            continue
        repo_cls(embedding_dim=dim, client=client).crear_coleccion()
        creadas.append(repo_cls.COLLECTION_NAME)
    return creadas


def main() -> None:
    settings = get_settings()
    # timeout holgado: crear índices de payload tarda más de 5 s en máquinas lentas o cargadas.
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60)
    creadas = crear_colecciones(client, settings.embedding_dim)
    print(f"✅ Creadas: {', '.join(creadas)}" if creadas else "✅ Las colecciones ya existen")


if __name__ == "__main__":
    main()
