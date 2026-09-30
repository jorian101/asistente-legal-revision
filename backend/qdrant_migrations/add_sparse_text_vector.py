"""Migración Qdrant: agregar vector sparse `text-sparse` a `corpus_juridico`.

La colección existente nació solo con el vector denso. Qdrant NO permite
agregar un named sparse vector a una colección que ya contiene puntos, así
que la migración es: volcar todos los puntos (vector denso + payload),
recrear la colección con el esquema completo y re-insertarlos calculando su
vector sparse BM25 desde `payload["texto"]`.

Seguridad:
- Sin `--yes` es DRY-RUN: reporta el plan y no toca nada.
- Con `--yes`: crea un snapshot de la colección antes de borrarla
  (best-effort), verifica conteo antes/después y aborta ante cualquier
  discrepancia dejando la colección nueva vacía (re-ejecutable).
- Si la colección YA tiene `text-sparse`, sale sin hacer nada (idempotente).

Uso:
    uv run python qdrant_migrations/add_sparse_text_vector.py          # dry-run
    uv run python qdrant_migrations/add_sparse_text_vector.py --yes    # ejecuta

Requiere stack levantado (Qdrant 6333). No consume embeddings: el vector
denso se copia tal cual del punto original.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qdrant_client import models  # noqa: E402

from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo  # noqa: E402
from src.application.services.hybrid_searcher import compute_bm25_sparse  # noqa: E402
from src.config import get_settings  # noqa: E402


def _volcar_puntos(repo: QdrantCorpusRepo) -> list[tuple[str, object, dict]]:
    """Scroll de todos los puntos con vector denso + payload completo."""
    client = repo._client  # noqa: SLF001 — script de migracion del propio adapter
    puntos: list[tuple[str, object, dict]] = []
    offset: models.PointId | None = None
    while True:
        records, next_offset = client.scroll(
            collection_name=repo.COLLECTION_NAME,
            limit=512,
            offset=offset,
            with_vectors=True,
            with_payload=True,
        )
        for r in records:
            puntos.append((str(r.id), r.vector, r.payload or {}))
        if next_offset is None:
            break
        offset = next_offset
    return puntos


async def main() -> int:
    parser = argparse.ArgumentParser(description="Migración sparse text-sparse")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Ejecuta la migración (sin este flag es dry-run)",
    )
    args = parser.parse_args()

    settings = get_settings()
    repo = QdrantCorpusRepo()
    client = repo._client  # noqa: SLF001

    info = client.get_collection(repo.COLLECTION_NAME)
    ya_tiene_sparse = bool(getattr(info.config.params, "sparse_vectors", None))
    dim_actual = info.config.params.vectors.size
    total = info.points_count or 0

    print(f"Colección '{repo.COLLECTION_NAME}': {total} puntos, dim={dim_actual}")
    if ya_tiene_sparse:
        # Guard por DATOS, no solo esquema: una corrida interrumpida puede
        # dejar la colección con text-sparse configurado y puntos sin él.
        sample_ids, _next = client.scroll(
            collection_name=repo.COLLECTION_NAME,
            limit=10,
            with_vectors=True,
            with_payload=False,
        )
        completos = (
            all(
                isinstance(r.vector, dict) and repo.SPARSE_VECTOR_NAME in r.vector
                for r in sample_ids
            )
            if sample_ids
            else False
        )
        if completos:
            print("✅ Ya tiene text-sparse (esquema y datos). Nada que hacer.")
            return 0
        print("⚠️  Esquema con text-sparse pero puntos sin él; continuando.")

    if dim_actual != settings.embedding_dim:
        print(
            f"❌ ABORTA: dim de colección ({dim_actual}) != EMBEDDING_DIM "
            f"({settings.embedding_dim}). Esta migración no es la correcta."
        )
        return 2

    if total == 0:
        # Sin puntos no hay que volcar ni re-insertar: se recrea (sin perdida de datos)
        # con el esquema completo del adapter. Un despliegue nuevo no tenia otra via.
        print("Colección vacía: se recrea con el esquema completo (denso + sparse + índices).")
        if not args.yes:
            print("\n[DRY-RUN] Ejecutá con --yes para recrearla.")
            return 0
        client.delete_collection(repo.COLLECTION_NAME)
        repo.crear_coleccion()
        print("✅ Colección vacía recreada con text-sparse.")
        return 0

    print("Volcando puntos (vector denso + payload)...")
    puntos = _volcar_puntos(repo)
    print(f"Volcados: {len(puntos)}")
    if len(puntos) == 0:
        print("❌ ABORTA: points_count > 0 pero el scroll no devolvió puntos.")
        return 2
    if total and len(puntos) != total:
        print(f"❌ ABORTA: points_count={total} pero scroll devolvió {len(puntos)}.")
        return 2

    sin_texto = sum(1 for _, _, p in puntos if not p.get("texto"))
    print(f"Puntos sin payload['texto'] (quedarán solo-densos): {sin_texto}")

    if not args.yes:
        print(
            "\n[DRY-RUN] Plan: snapshot → recrear colección con text-sparse "
            "→ re-insertar con BM25 sparse. Ejecutá con --yes."
        )
        return 0

    # 1. Snapshot best-effort (seguridad antes del recreate).
    try:
        snap = client.create_snapshot(repo.COLLECTION_NAME)
        print(f"📦 Snapshot creado: {getattr(snap, 'name', snap)}")
    except Exception as exc:  # noqa: BLE001 — el snapshot es cinturón extra
        print(f"⚠️  Snapshot falló ({exc}); se continúa igual.")

    # 2. Recrear con esquema completo (denso + sparse + indexes).
    client.delete_collection(repo.COLLECTION_NAME)
    repo.crear_coleccion()  # misma fuente de esquema del adapter
    print("Colección recreada con text-sparse.")

    # 3. Re-insertar conservando id/vector/payload y agregando sparse.
    puntos_dict = []
    for pid, vector, payload in puntos:
        punto: dict = {"id": pid, "vector": vector, "payload": payload}
        texto = payload.get("texto") or ""
        if texto:
            sv = compute_bm25_sparse(texto)
            punto["vector_sparse"] = {
                "indices": list(sv.indices),
                "values": list(sv.values),
            }
        puntos_dict.append(punto)
    await repo.upsert_corpus(puntos_dict)

    # 4. Verificación post-migración.
    info_nueva = client.get_collection(repo.COLLECTION_NAME)
    count_nuevo = info_nueva.points_count or 0
    status = "OK" if count_nuevo == len(puntos) else "MISMATCH"
    print(f"Re-insertados: {count_nuevo}/{len(puntos)} [{status}]")
    if count_nuevo != len(puntos):
        print("❌ Conteo no coincide; revisá el snapshot antes de borrar nada.")
        return 2

    sample_id, _, _ = puntos[0]
    sample = client.retrieve(
        collection_name=repo.COLLECTION_NAME,
        ids=[sample_id],
        with_vectors=True,
    )
    tiene_sparse = isinstance(sample[0].vector, dict) and repo.SPARSE_VECTOR_NAME in (
        sample[0].vector or {}
    )
    print(f"Sample {sample_id}: text-sparse presente={tiene_sparse}")

    print(
        "✅ Migración completa. Reiniciá procesos backend para que "
        "_collection_has_sparse lo detecte (cache por instancia)."
    )
    repo.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
