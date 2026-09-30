"""CLI: ingest_corpus.py — Indexa una norma completa desde PDF.

Uso:
    uv run python scripts/ingest_corpus.py --abreviatura CPPM --pdf /ruta/archivo.pdf

Variables de entorno requeridas (.env):
    POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT
    QDRANT_PORT, SECRET_KEY, LLM_PROVIDER, OLLAMA_HOST
    EMBEDDING_MODEL_NAME, EMBEDDING_DIM, EMBEDDING_TEXT_BATCH_SIZE
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Asegurar que el directorio backend/ esté en el path para importar 'src'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Auto-registro de segmentadores (efecto lateral al importar)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import src.domain.services.segmentacion.cpe  # noqa: F401
import src.domain.services.segmentacion.cpm  # noqa: F401
import src.domain.services.segmentacion.cppm  # noqa: F401
import src.domain.services.segmentacion.ley1970  # noqa: F401
import src.domain.services.segmentacion.lofa  # noqa: F401
import src.domain.services.segmentacion.lojm  # noqa: F401
from scripts._aviso import aviso_poblar  # noqa: E402
from src.adapters.ollama.ollama_embedder import OllamaEmbedder
from src.adapters.postgres.repos.fragmento_repo import FragmentoRepoImpl
from src.adapters.postgres.repos.norma_repo import SqlNormaRepo
from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo
from src.application.corpus.indexar_norma import IndexarNorma, IndexarNormaRequest
from src.application.ports.text_extractor import create_text_extractor
from src.config import get_settings


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Indexa una norma jurídica en corpus (PostgreSQL + Qdrant)"
    )
    parser.add_argument(
        "--abreviatura",
        required=True,
        help="Abreviatura canónica (CPPM, CPM, LOJM, LOFA, CPE, CP, CPP)",
    )
    parser.add_argument(
        "--pdf",
        required=True,
        type=Path,
        help="Ruta al archivo PDF de la norma",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Versión/texto legal (ej: 'Decreto Ley 13321')",
    )
    parser.add_argument(
        "--usuario",
        type=int,
        default=None,
        help="ID del usuario que dispara la indexación",
    )
    parser.add_argument(
        "--mode",
        choices=["raw", "markdown"],
        default="raw",
        help="Modo de extracción PyMuPDF (default: raw)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Batch size para embeddings (default: Settings.embedding_text_batch_size)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo extrae y segmenta, no persiste",
    )

    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"❌ PDF no encontrado: {args.pdf}")
        return 1

    # Validar abreviatura contra registry
    from src.domain.services.segmentacion.registro import SegmentadorRegistry

    if args.abreviatura not in SegmentadorRegistry.disponibles():
        print(f"❌ Abreviatura no soportada: {args.abreviatura}")
        print(f"   Disponibles: {SegmentadorRegistry.disponibles()}")
        return 1

    # Setup settings
    settings = get_settings()

    # Inicializar dependencias
    text_extractor = create_text_extractor(mode=args.mode)
    embedder = OllamaEmbedder(batch_size=args.batch_size)
    vector_repo = QdrantCorpusRepo()

    print(f"📄 Iniciando indexación: {args.abreviatura} desde {args.pdf}")
    print(f"   Modo extracción: {args.mode}")
    print(f"   Modelo embedding: {settings.embedding_model_name} ({settings.embedding_dim}d)")

    # Session factory para PostgreSQL async
    engine = create_async_engine(settings.postgres_url_async, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        # Asegurar colección Qdrant
        print("🔧 Verificando/creando colección Qdrant...")
        await vector_repo.ensure_collection()

        if args.dry_run:
            # Dry run: solo extraer y segmentar
            print("🏃 Dry run: extrayendo texto y segmentando...")
            result = await text_extractor.extract(args.pdf)
            from src.domain.services.segmentacion.base import limpiar_texto_ocr
            from src.domain.services.segmentacion.registro import SegmentadorRegistry

            segmentador = SegmentadorRegistry.obtener(args.abreviatura)
            texto = limpiar_texto_ocr(result.full_text)
            arbol = segmentador.segmentar(texto)

            print("✅ Dry run completado:")
            print(f"   Artículos segmentados: {len(arbol.fragmentos)}")
            print(f"   Nodos estructurales: {len(arbol.nodos)}")
            for frag in arbol.fragmentos[:5]:
                texto_len = len(frag.texto)
                print(
                    f"   - Art. {frag.metadatos.get('numero_articulo')}: "
                    f"{frag.tipo_chunk} ({texto_len} chars)"
                )
            return 0

        # Ejecución real con repos PostgreSQL
        async with async_session() as session:
            norma_repo = SqlNormaRepo(session)
            fragmento_repo = FragmentoRepoImpl(session)

            interactor = IndexarNorma(
                text_extractor=text_extractor,
                embedder=embedder,
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

            print("🚀 Ejecutando indexación completa...")
            response = await interactor.ejecutar(request)

            # Commit explicito — SQLAlchemy async no autocommitea
            await session.commit()

            print("✅ Indexación completada:")
            print(f"   Norma ID: {response.norma_id}")
            print(f"   Fragmentos creados: {response.fragmentos_creados}")
            print(f"   Vectores indexados en Qdrant: {response.vectores_indexados}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        await embedder.close()
        await engine.dispose()

    aviso_poblar()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
