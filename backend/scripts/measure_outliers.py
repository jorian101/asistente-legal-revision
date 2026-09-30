#!/usr/bin/env python3
"""Medicion de outliers del corpus juridico indexado.

Recorre la tabla `fragmento` (PostgreSQL) y reporta distribucion de tokens
estimados por fragmento + outliers en 4 umbrales relevantes:
- > 300 tokens  (rango de la tesis para fuentes normativas: 80-300)
- > 512 tokens  (mitad del limite alto del reranker BGE-M3)
- > 8000 chars  (limite ciego actual en OllamaEmbedder)
- > 28555 chars (peor caso observado Sprint 0: Art. 442 CPP)

Esto es entrada de datos para decidir la granularidad en Sprint 1
(la tesis pide numeral aislado, el codigo actual divide por articulo).

Uso:
    uv run --project backend python backend/scripts/measure_outliers.py

Salida: tabla stdout por corpus + outliers. Si queres persistir,
redirigir a archivo.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

# Habilita imports de src.config
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg

from src.config import Settings  # noqa: E402

CHARS_PER_TOKEN = 3.5  # heuristica para espanol: ~1.3 tokens por palabra media ~4.5 chars


def _build_dsn() -> str:
    s = Settings()  # sin lru_cache para evitar stales en re-run
    # postgres_url ya devuelve "postgresql+psycopg://"; psycopg3 acepta esa forma.
    # Pero psycopg.connect espera "postgresql://" plana. Quitamos el "+psycopg".
    url = s.postgres_url
    return url.replace("postgresql+psycopg://", "postgresql://")


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    idx = max(0, min(len(sorted_values) - 1, int(p * (len(sorted_values) - 1))))
    return sorted_values[idx]


def main() -> int:
    dsn = _build_dsn()

    query = """
        SELECT
            n.abreviatura AS corpus,
            LENGTH(f.texto) AS char_len,
            f.nivel_jerarquico
        FROM fragmento f
        JOIN norma n ON n.id = f.norma_id
        WHERE n.abreviatura IS NOT NULL
    """

    per_corpus_chars: dict[str, list[int]] = defaultdict(list)
    total_count = 0

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(query)
        for corpus, char_len, _nivel in cur.fetchall():
            per_corpus_chars[corpus].append(int(char_len))
            total_count += 1

    if not per_corpus_chars:
        print("No se encontraron fragmentos en la tabla.")
        return 1

    print(f"=== Distribucion por corpus ({total_count} fragmentos) ===\n")
    print(
        f"{'corpus':<12} {'n':>5} {'p50':>7} {'p90':>7} {'p99':>7} {'max':>7} {'>300tok':>9} {'>8000':>7}"
    )
    print("-" * 80)

    thresholds_chars = {
        ">300tok (tema tesis)": int(300 * CHARS_PER_TOKEN),
        ">512tok (mid reranker)": int(512 * CHARS_PER_TOKEN),
        ">8000 (limite embedder)": 8000,
        ">28555 (peor caso SP0)": 28555,
    }

    summary_outliers: dict[str, dict[str, list[tuple[str, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for corpus in sorted(per_corpus_chars):
        chars = sorted(per_corpus_chars[corpus])
        n = len(chars)
        p50 = _percentile(chars, 0.5)
        p90 = _percentile(chars, 0.9)
        p99 = _percentile(chars, 0.99)
        mx = chars[-1]

        n_over_300tok = sum(1 for c in chars if c > thresholds_chars[">300tok (tema tesis)"])
        n_over_8000 = sum(1 for c in chars if c > thresholds_chars[">8000 (limite embedder)"])

        print(
            f"{corpus:<12} {n:>5} {p50:>7.0f} {p90:>7.0f} {p99:>7.0f} {mx:>7} {n_over_300tok:>9} {n_over_8000:>7}"
        )

        # guardar outliers por threshold para detalle
        for label, thr in thresholds_chars.items():
            for c in chars:
                if c > thr:
                    summary_outliers[label][corpus].append(("?", c))

    print("\n=== Outliers por umbral ===")
    for label, thr in thresholds_chars.items():
        total = sum(len(v) for v in summary_outliers[label].values())
        print(
            f"\n{label} (> {thr} chars; > {thr / CHARS_PER_TOKEN:.0f} tok estimados): {total} outliers"
        )
        for corpus in sorted(summary_outliers[label]):
            outs = summary_outliers[label][corpus]
            tops = sorted(outs, key=lambda x: -x[1])[:5]
            print(f"  {corpus}: {len(outs)} outliers, top 5 max_chars: {[t[1] for t in tops]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
