#!/usr/bin/env python3
"""Migracion Qdrant: Crea la coleccion `corpus_juridico` con configuracion optima.

Idempotente: si la coleccion ya existe con la misma dimension, no hace nada.
Si existe con dimension distinta, exige SAFETY_ALLOW_COLLECTION_RECREATE=1: con el
permiso, intenta un snapshot y la borra y recrea; sin el, aborta sin tocar nada.
Ejecutar: `uv run python qdrant_migrations/create_corpus_juridico_collection.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qdrant_client import QdrantClient  # noqa: E402

from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo  # noqa: E402
from src.config import get_settings  # noqa: E402

COLLECTION_NAME = "corpus_juridico"


def _create_collection(client: QdrantClient, dim: int) -> None:
    """Crea la coleccion con el esquema completo del adapter (denso + sparse + indices).

    Antes duplicaba el esquema sin `text-sparse` ni los indices de privacidad, y la
    busqueda hibrida degradaba a densa sin avisar.
    """
    QdrantCorpusRepo(embedding_dim=dim, client=client).crear_coleccion()


def create_collection() -> None:
    """Crea la coleccion `corpus_juridico` si no existe o si la dim difiere."""
    settings = get_settings()
    desired_dim = settings.embedding_dim

    # timeout holgado: crear índices de payload tarda más de 5 s en máquinas lentas o cargadas.
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60)

    existing = client.get_collections().collections
    names = {c.name for c in existing}
    if COLLECTION_NAME not in names:
        _create_collection(client, desired_dim)
        print(f"✅ Coleccion '{COLLECTION_NAME}' creada exitosamente")
        print(f"   Vector size: {desired_dim}")
        print("   Distance: Cosine")
        print("   on_disk_payload: True")
        print("   Quantization: INT8 scalar")
        return

    # Existe: verificar dimension
    info = client.get_collection(COLLECTION_NAME)
    current_dim = info.config.params.vectors.size
    if current_dim == desired_dim:
        print(f"✅ Coleccion '{COLLECTION_NAME}' ya existe (dim={current_dim})")
        return

    # Mismatch: operacion destructiva, bloqueada por defecto (igual que el adapter
    # QdrantCorpusRepo) para no borrar el corpus por cambiar EMBEDDING_DIM sin querer.
    if not settings.safety_allow_collection_recreate:
        raise RuntimeError(
            f"Dimension mismatch en Qdrant: actual={current_dim} deseada={desired_dim} "
            f"(coleccion '{COLLECTION_NAME}'). Recreacion BLOQUEADA por "
            "SAFETY_ALLOW_COLLECTION_RECREATE=false. Para migrar el modelo de embedding, "
            "setea SAFETY_ALLOW_COLLECTION_RECREATE=1 y reejecuta la ingesta."
        )

    print(f"⚠️  WARNING: dimension mismatch detected (actual={current_dim}, deseada={desired_dim}).")
    # Snapshot best-effort antes de borrar (el permiso ya fue dado explicitamente).
    try:
        snap = client.create_snapshot(COLLECTION_NAME)
        print(f"📦 Snapshot previo creado: {getattr(snap, 'name', snap)}")
    except Exception as exc:  # noqa: BLE001 — cinturon extra, no bloquea el permiso dado
        print(f"⚠️  El snapshot previo fallo ({exc}); se continua igual.")
    print(f"   Borrando coleccion vieja y recreando con dim={desired_dim}...")
    client.delete_collection(COLLECTION_NAME)
    _create_collection(client, desired_dim)
    print(f"✅ Coleccion '{COLLECTION_NAME}' recreada con dim={desired_dim}")
    print("   Distance: Cosine")
    print("   on_disk_payload: True")
    print("   Quantization: INT8 scalar")


if __name__ == "__main__":
    try:
        create_collection()
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
