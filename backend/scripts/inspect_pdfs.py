#!/usr/bin/env python3
"""Script de inspección: extrae artículos clave de cada PDF con PyMuPDF.

Uso:
    uv run --project backend python backend/scripts/inspect_pdfs.py

Extrae 1-2 páginas por PDF que contienen los artículos representativos
de cada rama de segmentación. Muestra tanto modo RAW (bloques con coords)
como MARKDOWN (pymupdf4llm).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Asegurar que el directorio backend/ esté en el path para poder importar 'src'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.adapters.file_extractor import create_text_extractor

# Rutas a los PDFs en Zotero/WSL
PDF_PATHS = {
    "CPPM": Path(
        "/mnt/d/Archivos/Zotero/storage/AKKW55I7/CODIGO DE PROCEDIMIENTO PENAL MILITAR.doc.pdf"
    ),
    "CPM": Path("/mnt/d/Archivos/Zotero/storage/RDNJ5SZ4/CODIGO PENAL MILITAR.doc.pdf"),
    "LOJM": Path(
        "/mnt/d/Archivos/Zotero/storage/9NQG9HNB/LEY DE ORGANIZACION JUDICIAL MILITAR.doc.pdf"
    ),
    "LOFA": Path(
        "/mnt/d/Archivos/Zotero/storage/HCIBCX47/LEY ORGÁNICA DE LAS FUERZAS ARMADAS DE LA NACIÓN.docx.pdf"
    ),
    "CPE": Path("/mnt/d/Archivos/Zotero/storage/HQWPHUI8/CPE.pdf"),
    "LEY1970": Path(
        "/mnt/d/Archivos/Zotero/storage/4KKLRFG9/codigo-penal-y-procedimento-penal.pdf"
    ),
}

# Páginas objetivo por corpus (1-indexed) — basadas en pdftotext inspección previa
# Ajustar después de ver el output real
TARGET_PAGES = {
    "CPPM": [2, 3],  # Art. 22 (numerales) + Art. 25 (términos, sin numerales)
    "CPM": [2, 3],  # Art. 178 (12 numerales) - verificar página exacta
    "LOJM": [3, 4],  # Art. 38 (Atribuciones) + Art. 15 (párrafos sueltos)
    "LOFA": [2, 3],  # Art. 40 (incisos con subnumerales) + Art. 113 (categorías)
    "CPE": [3, 4],  # Art. 8 (parágrafos I, II) + Art. 10 (numerales)
    "LEY1970": [12, 13],  # Art. 47 (texto + nota modificado) - verificar
}

OUTPUT_DIR = Path(__file__).parent / ".tmp" / "inspect"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def inspect_pdf(corpus: str, pdf_path: Path, pages: list[int]) -> None:
    """Extrae y guarda ambos modos para las páginas dadas."""
    print(f"\n{'=' * 70}")
    print(f"  INSPECCIÓN: {corpus}")
    print(f"  Archivo: {pdf_path.name}")
    print(f"  Páginas: {pages}")
    print(f"{'=' * 70}")

    if not pdf_path.exists():
        print(f"  ❌ NO ENCONTRADO: {pdf_path}")
        return

    extractor_raw = create_text_extractor(mode="raw")
    extractor_md = create_text_extractor(mode="markdown")

    try:
        # Modo RAW
        raw_result = await extractor_raw.extract_pages(pdf_path, pages)
        raw_file = OUTPUT_DIR / f"{corpus}_raw.txt"
        raw_file.write_text(raw_result.full_text, encoding="utf-8")
        print(f"\n  📄 MODO RAW (blocks con coords) → {raw_file}")
        print(f"     Páginas extraídas: {len(pages)} / {raw_result.pages_count} total")
        print(f"     Bloques: {len(raw_result.blocks) if raw_result.blocks else 0}")
        # Mostrar primeros 2000 chars
        preview = raw_result.full_text[:2000]
        print("\n     --- PREVIEW RAW ---")
        print(preview)
        print("     --- FIN PREVIEW ---")

        # Modo MARKDOWN
        md_result = await extractor_md.extract_pages(pdf_path, pages)
        md_file = OUTPUT_DIR / f"{corpus}_markdown.md"
        md_file.write_text(md_result.full_text, encoding="utf-8")
        print(f"\n  📝 MODO MARKDOWN (pymupdf4llm) → {md_file}")
        preview_md = md_result.full_text[:2000]
        print("\n     --- PREVIEW MARKDOWN ---")
        print(preview_md)
        print("     --- FIN PREVIEW ---")

    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        import traceback

        traceback.print_exc()


async def main() -> int:
    print("🔍 Inspección de PDFs con PyMuPDF (raw + markdown)")
    print(f"Directorio de salida: {OUTPUT_DIR}")

    for corpus, pdf_path in PDF_PATHS.items():
        pages = TARGET_PAGES.get(corpus, [1])
        await inspect_pdf(corpus, pdf_path, pages)

    print(f"\n✅ Inspección completa. Archivos en: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
