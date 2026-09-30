#!/usr/bin/env python3
"""Genera formato.json alineado a las variables de la plantilla del asistente.

Para auto_vista y dictamen_radicatoria: el formato TSJM real debe cumplir
las plantillas del asistente (docs/plantillas/*.md). Este script mapea los
bloques de identificación del layout.json real a las variables {{...}} que
usa el asistente, manteniendo el texto fijo (boilerplate) tal cual.

Uso: python3 gen_formato_plantilla.py <layout.json> <tipo> --vars "clave=regex"...
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Variables de la plantilla del asistente y cómo detectarlas en el layout.
# Las cabeceras reales contienen el texto; al detectarlo se reemplaza por {{VAR}}.
VARS_AUTO_VISTA = [
    ("{{AUTO_DE_VISTA_CORRELATIVO}}", r"[Nn][°º]?\s*\d+/\d{4}"),
    ("{{FECHA_ACTUAL}}", r"La Paz,\s*\d+\s+de\s+[a-záéíóúñ]+\s+de\s+\d{4}"),
    ("{{NUMERO_CASO}}", r"Expediente\s*[Nn]?[°º]?:?\s*\d+"),
    ("{{PROCESADO_GRADO_Y_NOMBRE}}", r"Procesado:?\s+.+"),
    ("{{VOCAL_RELATOR}}", r"Vocal Relator:?\s+.+"),
    ("{{DELITO_CONCRETO}}", r"Proceso:?\s+.+"),
]
VARS_RADICATORIA = [
    ("{{NUMERO_CASO}}", r"EXPEDIENTE\s*[Nn]?[°º]?\s*\d+"),
    ("{{FECHA_ACTUAL}}", r"La Paz,\s*\d+\s+de\s+[a-záéíóúñ]+\s+de\s+\d{4}"),
    ("{{CUERPO_FOJAS}}", r"Cuerpo\s*\d+\s*[Ff]s\.?\s*[\d\s]+\s*a\s*[Ff]s\.?\s*[\d\s]+"),
    ("{{HITO_PROCESAL_FOJA}}", r"^[Aa]\s*[Ff]s\.?\s*\d+"),
]


def _apply_vars(text: str, vars_spec: list[tuple[str, str]]) -> tuple[str, set[str]]:
    usadas = set()
    for var, pattern in vars_spec:
        if re.search(pattern, text, re.I):
            # reemplazar el match por la variable
            text = re.sub(pattern, var, text, flags=re.I)
            usadas.add(var)
    return text, usadas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("layout_json", type=Path)
    ap.add_argument("tipo", choices=["auto_vista", "dictamen_radicatoria"])
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--autor", default="tsjm")
    args = ap.parse_args()

    vars_spec = VARS_AUTO_VISTA if args.tipo == "auto_vista" else VARS_RADICATORIA
    data = json.loads(args.layout_json.read_text(encoding="utf-8"))
    bloques = []
    placeholders = set()
    for b in data.get("blocks", []):
        texto_original = "".join(r.get("text", "") for r in b.get("runs", []))
        # aplicar variables al bloque; si cambió, es bloque variable
        texto_vars, usadas = _apply_vars(texto_original, vars_spec)
        placeholders |= usadas
        if usadas:
            # marcamos el bloque como plantilla (solo texto con variable)
            bloques.append({
                "kind": b.get("kind", "paragraph"),
                "page": b.get("page", 1),
                "index": b.get("index", 0),
                "align": b.get("align", "left"),
                "template": True,
                "texto_plantilla": texto_vars,
                "runs": b.get("runs", []),
            })
        else:
            # bloque fijo (boilerplate) o considerando
            bloques.append({
                "kind": b.get("kind", "paragraph"),
                "page": b.get("page", 1),
                "index": b.get("index", 0),
                "align": b.get("align", "left"),
                "template": False,
                "runs": b.get("runs", []),
            })

    formato = {
        "tipo_documento": args.tipo,
        "autor": args.autor,
        "fuente_layout": str(args.layout_json),
        "alineado_plantilla_asistente": True,
        "esqueleto": bloques,
        "placeholders": sorted(placeholders),
        "nota": ("Formato alineado a docs/plantillas. Los bloques template=true "
                 "llevan variables del asistente {{...}}; los fixed son boilerplate."),
    }

    out = args.out or args.layout_json.parent / "formato.json"
    out.write_text(json.dumps(formato, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK {out} — {len(bloques)} bloques, placeholders: {sorted(placeholders)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())