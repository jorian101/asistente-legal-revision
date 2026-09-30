"""Consenso Docling×Paddle: confianza por bloque vía contención de tokens.

Cada bloque de Docling se contrasta contra las líneas OCR del segundo motor
(misma página). Contención alta = ambos motores leen lo mismo -> confianza
sube; baja o vacío -> `review: true` para la cola humana.
"""
from __future__ import annotations

import re
import unicodedata

_NGRAM = 4


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _tokens(s: str) -> set[str]:
    """4-gramas de palabras; textos cortos caen a palabras sueltas."""
    t = _norm(s).split()
    if not t:
        return set()
    if len(t) < _NGRAM:
        return set(t)
    return {" ".join(t[i:i + _NGRAM]) for i in range(len(t) - _NGRAM + 1)}


def aplicar_consenso(layout: dict, paddle_json: dict,
                     umbral_review: float = 0.55) -> int:
    # ref por página: palabras sueltas (robusto a cortes de línea)
    por_pagina: dict[int, set[str]] = {}
    for p in paddle_json.get("pages", []):
        texto = " ".join(l["text"] for l in p["lines"])
        por_pagina[p["page"]] = set(_norm(texto).split())

    revisados = 0
    for b in layout["blocks"]:
        texto = "".join(r["text"] for r in b.get("runs", []))
        # bloques: palabras sueltas para bloques cortos, 4-gramas para largos (precisión)
        # pero ref es palabras -> comparar a nivel palabra siempre
        toks = set(_norm(texto).split())
        ref = por_pagina.get(b["page"], set())
        if not toks:
            b["confidence"] = 0.5
            continue
        contencion = len(toks & ref) / len(toks)
        base = b.get("confidence", 0.8)
        b["confidence"] = round(min(0.99, base * 0.5 + 0.5 * contencion), 2)
        if b["confidence"] < umbral_review:
            b["review"] = True
            revisados += 1
    layout["meta"]["consenso"] = {
        "motor2": paddle_json.get("engine"),
        "rss_peak_mb_motor2": paddle_json.get("rss_peak_mb"),
        "bloques_en_revision": revisados,
    }
    return revisados
