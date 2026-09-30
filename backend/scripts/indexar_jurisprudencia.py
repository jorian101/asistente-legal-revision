"""CLI: indexar_jurisprudencia.py — Indexa una sentencia (N2) o libro (N3).

F2.3: lee el .txt del vault (sources/doctrina/raw/), lo pasa como
texto_directo a IndexarNorma (sin extractor PDF) y lo indexa en la
colección `jurisprudencia` (ficha N2, niveles-corpus).

Uso:
    uv run python scripts/indexar_jurisprudencia.py \
        --abreviatura SCP-0623-2024-S4 \
        --txt "/ruta/scp-0623-2024-s4.txt" [--yes]

Requiere stack levantado (PG 5433 + Qdrant 6333 + Ollama 11434).
Idempotente: si la abreviatura existe, avisa y sale (409 lógico);
con --yes borra PG+Qdrant y reindexa (mismo patrón que reindexar_norma).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.adapters.file_extractor import create_text_extractor
from src.adapters.http.dependencies import build_embedder
from src.adapters.postgres.models.norma import NormaModel
from src.adapters.postgres.repos.fragmento_repo import FragmentoRepoImpl
from src.adapters.postgres.repos.norma_repo import SqlNormaRepo
from src.adapters.qdrant.qdrant_jurisprudencia_repo import QdrantJurisprudenciaRepo
from src.application.corpus.indexar_norma import IndexarNorma, IndexarNormaRequest
from src.config import get_settings


async def main() -> int:
    parser = argparse.ArgumentParser(description="Indexa una sentencia en N2")
    parser.add_argument(
        "--abreviatura",
        required=True,
        help="Abreviatura propia (SCP-0623-2024-S4, CIDH-TC-PERU-2001)",
    )
    parser.add_argument("--txt", required=True, type=Path, help="Ruta al .txt")
    parser.add_argument("--usuario", type=int, default=None)
    parser.add_argument("--yes", action="store_true", help="Reindexar si existe")
    parser.add_argument(
        "--repo",
        choices=["jurisprudencia", "doctrina"],
        default="jurisprudencia",
        help="Colección destino (N2/N3)",
    )
    args = parser.parse_args()

    if not args.txt.exists():
        print(f"❌ TXT no encontrado: {args.txt}")
        return 1

    settings = get_settings()
    engine = create_async_engine(settings.postgres_url_async, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        if args.repo == "doctrina":
            from src.adapters.qdrant.qdrant_doctrina_repo import QdrantDoctrinaRepo

            vector_repo_juris = QdrantDoctrinaRepo()
        else:
            vector_repo_juris = QdrantJurisprudenciaRepo()
        await vector_repo_juris.ensure_collection()
        async with async_session() as session:
            norma_repo = SqlNormaRepo(session)
            fragmento_repo = FragmentoRepoImpl(session)

            existente = await norma_repo.get_by_abreviatura(args.abreviatura)
            if existente is not None:
                if not args.yes:
                    print(
                        f"ℹ️  Ya existe '{args.abreviatura}' "
                        f"(id={existente.id}). Usa --yes para reindexar."
                    )
                    return 0
                await fragmento_repo.delete_by_norma(existente.id)
                await vector_repo_juris.delete_by_norma(existente.id)
                await session.execute(delete(NormaModel).where(NormaModel.id == existente.id))
                await session.commit()
                print("   ✓ limpieza completa (fragmentos PG + puntos Qdrant + fila)")

            interactor = IndexarNorma(
                text_extractor=create_text_extractor(mode="raw"),
                embedder=build_embedder(None),
                vector_repo=vector_repo_juris,
                norma_repo=norma_repo,
                fragmento_repo=fragmento_repo,
                vector_repo_jurisprudencia=vector_repo_juris,
                vector_repo_doctrina=vector_repo_juris,
            )
            if args.txt.suffix.lower() == ".pdf":
                import fitz

                doc = fitz.open(args.txt)
                texto = chr(10).join(p.get_text() for p in doc)
                doc.close()
            else:
                texto = args.txt.read_text(encoding="utf-8", errors="ignore")
            print(f"🚀 Indexando '{args.abreviatura}' ({len(texto)} chars)...")
            resp = await interactor.ejecutar(
                IndexarNormaRequest(
                    abreviatura=args.abreviatura,
                    ruta_pdf=args.txt,
                    indexado_por=args.usuario,
                    texto_directo=texto,
                )
            )
            await session.commit()

            print("✅ Indexación completada:")
            print(f"   Norma ID: {resp.norma_id}")
            print(f"   Fragmentos creados: {resp.fragmentos_creados}")
            print(f"   Vectores Qdrant: {resp.vectores_indexados}")
            print(f"   Colección: {resp.qdrant_collection}")
    finally:
        await engine.dispose()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
