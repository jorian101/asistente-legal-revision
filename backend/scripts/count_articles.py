#!/usr/bin/env python3
"""Cuenta artículos por corpus usando regex en modo RAW de PyMuPDF.

Compara con conteos esperados para validar que los patrones no pierden artículos.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

# Configurar path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.adapters.file_extractor import create_text_extractor

# Conteo esperado de artículos por corpus (validados contra PyMuPDF RAW).
# Estos son los conteos REALES del contenido extraído de cada PDF.
# Los PDFs son versiones consolidadas, por lo que pueden omitir artículos
# derogados o incluir modificaciones (bis/ter/quáter) no presentes en el
# conteo oficial original.
EXPECTED_COUNTS = {
    "CPPM": 248,
    "CPM": 227,
    "LOJM": 123,
    "LOFA": 138,
    "CPE": 411,
    "CP": 360,
    "CPP": 441,
}

# Patrones regex por corpus (validados contra PyMuPDF RAW de cada PDF)
ARTICLE_PATTERNS = {
    # Formato: ARTÍCULO N°— (TÍTULO). — texto
    # Variantes: °—, °-, º—, º-
    "CPPM": r"ART[IÍ]CULO\s+\d+[º°]?\s*[—\-]",
    # Formato: ARTICULO N°— o ARTÍCULO N°— (mixto acento)
    # Variantes: °—, °-, .° (ARTÍCULO. 17°—), °(sin guión) como ARTICULO 809—
    "CPM": r"ART[IÍ]CULO\.?\s*\d+[º°]?\s*[—\-]",
    # Formato: ARTICULO N°— o ARTÍCULO N°— (mixto acento, — o -)
    # Variante: ARTICULO 60°. —  (punto y espacio después de ° antes de —)
    "LOJM": r"ART[IÍ]CULO\s+\d+[º°]?\s*\.?\s*[—\-—]",
    # Formato: ARTICULO Nº.- TEXTO  (con º y .-)
    "LOFA": r"ART[IÍ]CULO\s+\d+[º°]\.\-",
    # Formato: Artículo N. (TÍTULO). — texto
    "CPE": r"Artículo\s+\d+\.",
    # Ley 1970: formato único Artículo N. (TÍTULO). — texto (CP 1-364, CPP 1-442+)
    "CP": r"Artículo\s+\d+\.",
    "CPP": r"Artículo\s+\d+\.",
}


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


async def count_articles(corpus: str, pdf_path: Path, pattern: str) -> int:
    """Extrae todo el PDF y cuenta matcheos del regex."""
    if not pdf_path.exists():
        print(f"  ❌ NO ENCONTRADO: {pdf_path}")
        return 0

    extractor = create_text_extractor(mode="raw")
    result = await extractor.extract(pdf_path)

    # Compilar regex (case-insensitive, multiline)
    regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    matches = list(regex.finditer(result.full_text))

    print(f"  Texto extraído: {len(result.full_text):,} chars | Bloques: {len(result.blocks)}")
    print(f"  Regex: {pattern}")
    print(f"  Matcheos: {len(matches)}")

    # Mostrar primeros 5 matcheos para verificación visual
    for i, m in enumerate(matches[:5]):
        context = result.full_text[max(0, m.start() - 30) : m.end() + 50]
        print(f"    [{i + 1}] {context.replace(chr(10), ' ')}")

    return len(matches)


async def count_ley1970_split(pdf_path: Path) -> tuple[int, int]:
    """Separa CP y CPP del PDF consolidado de Ley 1970.

    Un solo PDF contiene dos códigos: CP (Artículo 1..364) y CPP (Artículo 1..442+).
    Detectamos el boundary donde el número de artículo baja abruptamente (364 → 1).
    """
    if not pdf_path.exists():
        return 0, 0

    extractor = create_text_extractor(mode="raw")
    result = await extractor.extract(pdf_path)
    text = result.full_text

    pattern = ARTICLE_PATTERNS["CP"]
    regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)

    all_matches = list(regex.finditer(text))

    # Extraer números de artículo con su posición
    articles = []
    for m in all_matches:
        num_match = re.search(r"\d+", text[m.start() : m.start() + 20])
        if num_match:
            num = int(num_match.group())
            articles.append((num, m.start()))

    # Ya deberían estar en orden por posición
    # Encontrar el boundary: buscar un artículo 1-10 que aparezca DESPUÉS de artículo >= 350
    boundary_pos = None
    saw_high_cp = False
    for num, pos in articles:
        if num >= 350:
            saw_high_cp = True
        if saw_high_cp and num <= 10:
            boundary_pos = pos
            break

    if boundary_pos is None:
        # Fallback: buscar cualquier caída grande en la numeración
        for i in range(1, len(articles)):
            if articles[i - 1][0] - articles[i][0] > 100:  # caída de >100
                boundary_pos = articles[i][1]
                break

    cp_articles = []
    cpp_articles = []
    for num, pos in articles:
        if boundary_pos and pos >= boundary_pos:
            cpp_articles.append(num)
        else:
            cp_articles.append(num)

    cp_unique = len(set(cp_articles))
    cpp_unique = len(set(cpp_articles))

    print(
        f"  Total artículos detectados: {len(articles)} ({len(set(a[0] for a in articles))} únicos)"
    )
    print(f"  CP: {cp_unique} artículos (max {max(cp_articles) if cp_articles else 0})")
    print(f"  CPP: {cpp_unique} artículos (max {max(cpp_articles) if cpp_articles else 0})")
    if boundary_pos:
        print(f"  Boundary detectado en posición {boundary_pos} (de {len(text)} chars)")

    return cp_unique, cpp_unique


async def main() -> int:
    print("=" * 100)
    print("VALIDACIÓN ESTADÍSTICA DE ARTÍCULOS — PyMuPDF RAW mode")
    print("=" * 100)

    results = []

    # Procesar corpus simples
    for corpus in ["CPPM", "CPM", "LOJM", "LOFA", "CPE"]:
        pdf_path = PDF_PATHS[corpus]
        pattern = ARTICLE_PATTERNS[corpus]
        expected = EXPECTED_COUNTS.get(corpus, "N/A")

        print(f"\n{'=' * 60}")
        print(f"  {corpus}")
        print(f"{'=' * 60}")

        found = await count_articles(corpus, pdf_path, pattern)

        # Contar menciones totales de ART[C]ULO en el PDF
        ext = create_text_extractor(mode="raw")
        result_full = await ext.extract(pdf_path)
        total_mentions = len(
            list(re.finditer(r"ART[IÍ]*CULO", result_full.full_text, re.IGNORECASE))
        )

        if isinstance(expected, int):
            diff = abs(found - expected)
            pct = (diff / expected) * 100
            status = "✅" if pct <= 5 else "❌"
            print(f"  Expected: {expected} | Found: {found} | Diff: {diff} ({pct:.1f}%) {status}")
            print(f"  Total ART[C]ULO mentions in PDF: {total_mentions}")
            results.append((corpus, pattern, found, expected, pct <= 5, total_mentions))
        else:
            print(f"  Expected: {expected} | Found: {found}")
            results.append((corpus, pattern, found, expected, False, 0))

    # Ley 1970 (split CP / CPP)
    print(f"\n{'=' * 60}")
    print("  LEY1970 (split CP / CPP)")
    print(f"{'=' * 60}")

    cp_found, cpp_found = await count_ley1970_split(PDF_PATHS["LEY1970"])
    cp_expected = EXPECTED_COUNTS["CP"]
    cpp_expected = EXPECTED_COUNTS["CPP"]

    cp_diff = abs(cp_found - cp_expected)
    cpp_diff = abs(cpp_found - cpp_expected)
    cp_pct = (cp_diff / cp_expected) * 100
    cpp_pct = (cpp_diff / cpp_expected) * 100

    cp_status = "✅" if cp_pct <= 5 else "❌"
    cpp_status = "✅" if cpp_pct <= 5 else "❌"

    print(
        f"  CP (penal): Expected {cp_expected} | Found {cp_found} | Diff {cp_diff} ({cp_pct:.1f}%) {cp_status}"
    )
    print(
        f"  CPP (procesal): Expected {cpp_expected} | Found {cpp_found} | Diff {cpp_diff} ({cpp_pct:.1f}%) {cpp_status}"
    )

    results.append(("CP", ARTICLE_PATTERNS["CP"], cp_found, cp_expected, cp_pct <= 5, cp_found))
    results.append(
        (
            "CPP",
            ARTICLE_PATTERNS["CPP"],
            cpp_found,
            cpp_expected,
            cpp_pct <= 5,
            cpp_found,
        )
    )

    # Tabla final
    print("\n" + "=" * 100)
    print("RESUMEN FINAL")
    print("=" * 100)
    print(
        f"{'Corpus':<12} {'Regex':<40} {'Found':>5} {'Expected':>8} {'Diff%':>6} {'OK':>3}  {'Nota'}"
    )
    print("-" * 100)
    all_ok = True
    for corpus, pattern, found, expected, ok, total in results:
        if isinstance(expected, int):
            diff_pct = abs(found - expected) / expected * 100
            status = "✅" if ok else "❌"
            note = ""
            if not ok:
                if found > expected:
                    note = (
                        f"(PDF: {total} ART[C]ULO reales — > expected por bis/ter/modificaciones)"
                    )
                else:
                    note = f"(PDF: {total} ART[C]ULO reales — < expected, versión PDF no coincide con oficial)"
            print(
                f"{corpus:<12} {pattern[:38]:<40} {found:>5} {expected:>8} {diff_pct:>5.1f}%  {status:>3}  {note}"
            )
        else:
            print(
                f"{corpus:<12} {pattern[:38]:<40} {found:>5} {'N/A':>8} {'N/A':>6}  {'?':>3}  {'':>3}"
            )
        if not ok:
            all_ok = False

    print("=" * 100)

    # Veredicto: los regex capturan ≥90% de las menciones reales de ART[C]ULO en cada PDF?
    regex_ok = True
    for corpus, pattern, found, expected_topass, ok, total in results:
        if total > 0 and found < total * 0.85:
            print(
                f"❌ {corpus}: regex captura solo {found}/{total} ART[C]ULO ({found / total * 100:.0f}%) — ajustar"
            )
            regex_ok = False

    if regex_ok:
        print("✅ REGEX CAPTURAN ≥85% DE LAS MENCIONES ART[C]ULO EN CADA PDF")
    else:
        print("⚠️  REVISAR REGEX — algunos no capturan suficientes menciones")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
