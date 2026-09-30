#!/usr/bin/env python3
"""Genera formato.json (esqueleto con placeholders) desde un layout.json.

Detecta texto variable por regex y lo reemplaza por un placeholder
{{TIPO}}. No se usa en formatos de auto_vista/dictamen_radicatoria
(esos se posponen: deben cumplir las plantillas del asistente).

Uso: python3 gen_formato.py <layout.json> <tipo_documento> [--out dir]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _is_variable(text: str) -> str | None:
    """Devuelve el placeholder si el texto es claramente variable, si no None."""
    t = text.strip()
    # Números de resolución/dictamen/sentencia: N° 28/2026, Nº 08/2025, N° 019/2026
    if re.fullmatch(r"([Nn]°?|Nº|No\.?)\s*\d+[/-]\d{4}", t):
        return "{{NUMERO_DOCUMENTO}}"
    # Expediente: EXPEDIENTE N° 3288 / Expediente 3288 / EXP. ACUMULADO
    if re.fullmatch(r"(EXPEDIENTE|EXP\.?)\s*(ACUMULADO\s*)?[Nn]?°?\s*\d+", t) or \
       re.fullmatch(r"Expediente\s*\d+", t):
        return "{{EXPEDIENTE}}"
    # Fecha literal: "La Paz, 03 de julio de 2026", "junio 18 de 2025"
    if re.search(r"\b(\d{1,2}\s+de\s+[a-záéíóúñ]+\s+de\s+\d{4}|de\s+[a-záéíóúñ]+\s+de\s+\d{4})", t, re.I):
        return "{{FECHA_LITERAL}}"
    # Cuerpo + fojas: "Cuerpo 1 Fs. 001 a Fs. 203"
    if re.fullmatch(r"Cuerpo\s*\d+\s*[Ff]s\.?\s*[\d\s]+\s*a\s*[Ff]s\.?\s*[\d\s]+", t):
        return "{{CUERPO_FOJAS}}"
    # "A fs. 373 de obrados, cursa..." - hitos procesales con foja (variable por caso)
    if re.match(r"^[Aa]\s*[Ff]s\.?\s*\d+", t):
        return "{{HITO_PROCESAL_FOJA}}"
    return None


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("layout_json", type=Path)
    ap.add_argument("tipo", help="TipoDocumento (ej. dictamen_fondo)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--autor", default="tsjm")
    args = ap.parse_args()

    data = json.loads(args.layout_json.read_text(encoding="utf-8"))
    bloques = []
    placeholders_usados = set()
    for b in data.get("blocks", []):
        runs = []
        texto_completo = "".join(r.get("text", "") for r in b.get("runs", []))
        var = _is_variable(texto_completo) if texto_completo else None
        if var:
            runs = [{"text": var, "bold": True, "italic": False,
                     "underline": False, "allcaps": False,
                     "size_pt": None, "font": None, "variable": True}]
            placeholders_usados.add(var)
        else:
            for r in b.get("runs", []):
                runs.append({
                    "text": r.get("text", ""),
                    "bold": bool(r.get("bold")),
                    "italic": bool(r.get("italic")),
                    "underline": bool(r.get("underline")),
                    "allcaps": bool(r.get("allcaps")),
                    "size_pt": r.get("size_pt"),
                    "font": r.get("font"),
                    "variable": False,
                })
        bloques.append({
            "kind": b.get("kind", "paragraph"),
            "page": b.get("page", 1),
            "index": b.get("index", 0),
            "align": b.get("align", "left"),
            "confidence": b.get("confidence", 1.0),
            "runs": runs,
        })

    formato = {
        "tipo_documento": args.tipo,
        "autor": args.autor,
        "fuente_layout": str(args.layout_json),
        "esqueleto": bloques,
        "placeholders": sorted(placeholders_usados),
        "variables_no_detectadas": [],  # para revisión humana
    }

    out = args.out or args.layout_json.parent / "formato.json"
    out.write_text(json.dumps(formato, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK {out} — {len(bloques)} bloques, placeholders: {sorted(placeholders_usados)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())