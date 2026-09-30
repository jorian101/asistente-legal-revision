"""CLI: reindex_embeddings.py — Recrea la colección y re-indexa el corpus.

Plan C (Fase 5): prepara la colección para soportar búsqueda híbrida real
(denso + sparse `text-sparse` BM25) y re-embebe las obras activas con el
modelo de embedding actual (o el indicado en --modelo).

ALERTA: recrear la colección BORRA los puntos actuales de Qdrant. Hacé un
respaldo antes (exportar puntos via snapshot Qdrant o dump de fragmentos).

UN EMBEDDING A LA VEZ (restricción de RAM): antes de reindexar con un modelo
nuevo, liberá el anterior con `ollama stop <modelo_anterior>`. El flujo es:
    1. ollama pull <modelo>
    2. editar .env (EMBEDDING_MODEL_NAME + EMBEDDING_DIM)
    3. ollama stop <modelo_anterior>
    4. uv run python scripts/reindex_embeddings.py --forzar
    5. re-indexar las normas (ingest_corpus.py por abreviatura)
    6. uv run python scripts/comparar_embeddings.py --evaluate

Uso:
    # Recrear colección con sparse y re-embeder TODAS las obras activas:
    uv run python scripts/reindex_embeddings.py --forzar

    # Con otro modelo (antes cambiar EMBEDDING_MODEL_NAME/EMBEDDING_DIM en .env):
    uv run python scripts/reindex_embeddings.py --forzar --modelo bge-m3 --dim 1024

    # Solo recrear la colección (sin re-embeder obras):
    uv run python scripts/reindex_embeddings.py --forzar --solo-coleccion

Para las NORMAS del corpus, después re-corré `ingest_corpus.py` por cada norma
(o el script batch que indexe el corpus completo).

El upsert de vectores sparse se activa automáticamente cuando la colección
tiene `text-sparse` configurado (QdrantCorpusRepo._upsert_corpus_sync lo
detecta en runtime). Requiere que la ingestión emita BM25 por fragmento.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import src.domain.services.segmentacion.cpe  # noqa: F401
import src.domain.services.segmentacion.cpm  # noqa: F401
import src.domain.services.segmentacion.cppm  # noqa: F401
import src.domain.services.segmentacion.ley1970  # noqa: F401
import src.domain.services.segmentacion.lofa  # noqa: F401
import src.domain.services.segmentacion.lojm  # noqa: F401
from src.adapters.http.dependencies import build_embedder
from src.adapters.postgres.repos.fragmento_repo import FragmentoRepoImpl
from src.adapters.postgres.repos.obra_repo import get_obra_repo
from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo
from src.application.expedientes.indexar_obra import IndexarObra
from src.config import get_settings


async def _recrear_coleccion() -> None:
    """Recrea la colección con sparse vector (pierde puntos actuales)."""
    repo = QdrantCorpusRepo()
    # QdrantCorpusRepo._create_collection define dense + sparse_vectors_config.
    # Se elimina y recrea para aplicar el sparse a una colección ya existente.
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels

    client = QdrantClient(host="127.0.0.1", port=6333)
    if client.collection_exists(repo.COLLECTION_NAME):
        client.delete_collection(repo.COLLECTION_NAME)
    client.create_collection(
        collection_name=repo.COLLECTION_NAME,
        vectors_config=qmodels.VectorParams(
            size=repo._dim,
            distance=qmodels.Distance.COSINE,
        ),
        sparse_vectors_config={
            repo.SPARSE_VECTOR_NAME: qmodels.SparseVectorParams(),
        },
        on_disk_payload=True,
    )
    print(
        f"✅ Colección '{repo.COLLECTION_NAME}' recreada con sparse "
        f"'{repo.SPARSE_VECTOR_NAME}' ({repo._dim}d)."
    )


async def _reindexar_obras(modelo_nombre: str) -> None:
    """Re-embebe todas las obras activas vía IndexarObra (idempotente)."""
    from sqlalchemy import select

    from src.adapters.postgres.models.obra import ObraModel

    settings = get_settings()
    engine = create_async_engine(settings.postgres_url_async)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    embedder = build_embedder(None)
    vector_repo = QdrantCorpusRepo()

    indexadas = 0
    errores = 0
    async with factory() as session:
        obra_repo = get_obra_repo(session)
        fragmento_repo = FragmentoRepoImpl(session)
        indexador = IndexarObra(
            obra_repo=obra_repo,
            fragmento_repo=fragmento_repo,
            embedder=embedder,
            vector_repo=vector_repo,
        )
        stmt = select(ObraModel).where(ObraModel.activo.is_(True))
        modelos = (await session.execute(stmt)).scalars().all()
        for model in modelos:
            obra = obra_repo._to_domain(model)
            try:
                resp = await indexador.ejecutar(obra)
                await session.commit()
                indexadas += 1
                print(f"  📄 {obra.nombre_archivo}: {resp.fragmentos_creados} frag")
            except Exception as exc:  # noqa: BLE001
                errores += 1
                print(f"  ❌ {obra.nombre_archivo}: {exc}")
                await session.rollback()

    await engine.dispose()
    print(
        f"\n✅ Obras re-indexadas: {indexadas}, errores: {errores} "
        f"(modelo activo: {modelo_nombre})."
    )


def _ollama_stop(modelo: str) -> None:
    """Descarga el modelo de la RAM (OLLAMA_KEEP_ALIVE=-1 lo deja cargado)."""
    import subprocess

    try:
        subprocess.run(
            ["ollama", "stop", modelo],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        print(f"🧹 ollama stop {modelo} — RAM liberada.")
    except FileNotFoundError:
        print("⚠️  'ollama' no está en PATH; la RAM no se liberó automáticamente.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Recrea colección + re-indexa embeddings")
    ap.add_argument(
        "--forzar",
        action="store_true",
        required=True,
        help="Recrear la colección (destructivo: borra puntos actuales)",
    )
    ap.add_argument(
        "--modelo", default=None, help="Nombre del modelo (info; el activo se lee de .env)"
    )
    ap.add_argument("--dim", type=int, default=None, help="Dimensiones del modelo activo")
    ap.add_argument(
        "--solo-coleccion",
        action="store_true",
        help="Solo recrear la colección, sin re-embeder obras",
    )
    args = ap.parse_args()

    if not args.forzar:
        ap.error("--forzar es obligatorio (la operación es destructiva)")

    if args.modelo:
        _ollama_stop(args.modelo)

    asyncio.run(_recrear_coleccion())

    if not args.solo_coleccion:
        modelo = args.modelo or "activo (.env EMBEDDING_MODEL_NAME)"
        asyncio.run(_reindexar_obras(modelo))
        print("\n⚠️  Para las NORMAS del corpus, re-corré ingest_corpus.py por norma.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
