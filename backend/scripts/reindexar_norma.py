"""CLI: reindexar_norma.py — Re-indexa una norma con el segmentador corregido.

P2.2: el fix de segmentacion (ordinal 'o' post-NFKC) recupero articulos del
corpus que nunca se indexaron (ej. CPPM Art. 194, base de la consulta de
oficio). Este script reemplaza los datos de una norma: borra fisicamente los
fragmentos (PG) + puntos (Qdrant) + la fila de norma vieja, y re-ingiere el
PDF completo con `IndexarNorma` (crea la norma nueva con todos los articulos).

Uso:
    uv run python scripts/reindexar_norma.py --abreviatura CPPM \
        --pdf "/ruta/CODIGO DE PROCEDIMIENTO PENAL MILITAR.doc.pdf"

Requiere stack levantado (PG 5433 + Qdrant 6333 + Ollama 11434). La norma
vuelve a ser embedida por completo (embedding local, sin APIs externas).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from scripts._aviso import aviso_poblar  # noqa: E402
from src.adapters.http.dependencies import build_embedder
from src.adapters.postgres.models.norma import NormaModel
from src.adapters.postgres.repos.fragmento_repo import FragmentoRepoImpl
from src.adapters.postgres.repos.norma_repo import SqlNormaRepo
from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo
from src.application.corpus.indexar_norma import IndexarNorma, IndexarNormaRequest
from src.application.ports.text_extractor import create_text_extractor
from src.config import get_settings


async def main() -> int:
    parser = argparse.ArgumentParser(description="Re-indexa una norma con limpieza previa")
    parser.add_argument("--abreviatura", required=True, help="Abreviatura (CPPM, CPM, LOJM, ...)")
    parser.add_argument("--pdf", required=True, type=Path, help="Ruta al PDF de la norma")
    parser.add_argument("--version", default=None, help="Version/texto legal")
    parser.add_argument("--usuario", type=int, default=None, help="ID del usuario indexador")
    parser.add_argument("--yes", action="store_true", help="Saltar confirmacion")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"❌ PDF no encontrado: {args.pdf}")
        return 1

    settings = get_settings()
    engine = create_async_engine(settings.postgres_url_async, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with async_session() as session:
            norma_repo = SqlNormaRepo(session)
            fragmento_repo = FragmentoRepoImpl(session)
            vector_repo = QdrantCorpusRepo()

            # 1. Localizar norma existente
            existente = await norma_repo.get_by_abreviatura(args.abreviatura)
            if existente is not None:
                print(f"ℹ️  Norma existente: id={existente.id} '{args.abreviatura}'")
                n_frag = await fragmento_repo.count_by_norma(existente.id)
                print(f"   fragmentos actuales: {n_frag}")
                if not args.yes:
                    r = input(
                        f"Borrar fisicamente norma id={existente.id} y sus {n_frag} "
                        f"fragmentos (PG+Qdrant) para reindexar? [y/N] "
                    )
                    if r.strip().lower() != "y":
                        print("Cancelado.")
                        return 0

                # 2. Borrar fisicamente fragmentos (PG) y puntos (Qdrant)
                await fragmento_repo.delete_by_norma(existente.id)
                await vector_repo.delete_by_norma(existente.id)

                # 3. Borrar fisicamente la fila de norma (UNIQUE abreviatura impide
                #    soft-delete + recrear). Sin FK: solo fragmento.norma_id referencia,
                #    y ya se borraron.
                await session.execute(delete(NormaModel).where(NormaModel.id == existente.id))
                await session.commit()
                print("   ✓ limpieza completa (fragmentos PG + puntos Qdrant + fila norma)")
            else:
                print(f"ℹ️  No existe norma '{args.abreviatura}': indexacion limpia.")

            # 4. Re-ingesta completa (crea la norma nueva)
            text_extractor = create_text_extractor(mode="raw")
            interactor = IndexarNorma(
                text_extractor=text_extractor,
                embedder=build_embedder(None),
                vector_repo=vector_repo,
                norma_repo=norma_repo,
                fragmento_repo=fragmento_repo,
            )
            request = IndexarNormaRequest(
                abreviatura=args.abreviatura,
                ruta_pdf=args.pdf,
                version=args.version,
                indexado_por=args.usuario,
            )
            print(f"🚀 Re-indexando '{args.abreviatura}' desde {args.pdf.name}...")
            resp = await interactor.ejecutar(request)
            await session.commit()

            print("✅ Reindexación completada:")
            print(f"   Norma ID: {resp.norma_id}")
            print(f"   Fragmentos creados: {resp.fragmentos_creados}")
            print(f"   Vectores Qdrant: {resp.vectores_indexados}")
    finally:
        await engine.dispose()

    aviso_poblar()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
