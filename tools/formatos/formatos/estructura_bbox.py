#!/usr/bin/env python3
"""Recalcula estructura de layout.json desde bbox (sin re-OCR).

Un scan (Docling) no conserva align ni size_pt. Pero el bbox sí tiene la
posición: el centro X del bloque vs centro de página da la alineación, y la
altura del bbox da un tamaño relativo. Este post-procesador recupera esa
fidelidad gratis sobre los layout.json ya extraídos.

Uso: python3 -m formatos.estructura_bbox <layout.json> [--write]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Tamaños de hoja en puntos (para centrar comparación)
HOJAS_PT = {
    "carta": (612.0, 792.0),    # 8.5x11 in
    "oficio": (612.0, 1008.0),  # 8.5x14 in (legal)
    "a4": (595.0, 842.0),       # 210x297 mm
}


def _page_width_pt(meta_page: dict) -> float:
    """Obtiene ancho de página en pt desde meta.page (mm o pt)."""
    w = meta_page.get("width_mm") or meta_page.get("width_pt")
    if not w:
        return 612.0  # default carta
    if "width_mm" in meta_page:
        return float(w) / 25.4 * 72.0
    return float(w)


def _normalizar_align(center_x: float, page_w: float, n_palabras: int) -> str:
    """Alineación combinando bbox + heurística textual.

    - Título/corto (n_palabras <= 6) cerca del centro → center.
    - Título/corto desplazado a la derecha → right.
    - Párrafo largo → justify (cuerpo).
    - Resto → left.
    """
    page_center = page_w / 2.0
    diff = abs(center_x - page_center)
    es_corto = n_palabras <= 6
    if es_corto and diff <= 25.0:
        return "center"
    if es_corto and center_x > page_center + 25.0:
        return "right"
    if n_palabras > 20:
        return "justify"
    return "left"


def recalcular(layout: dict) -> dict:
    """Reescribe align de cada bloque combinando bbox y heurística textual."""
    page_w = _page_width_pt(layout.get("meta", {}).get("page", {}))

    for b in layout.get("blocks", []):
        texto = "".join(r.get("text", "") for r in b.get("runs", []))
        n_palabras = len(texto.split())
        bb = b.get("bbox")
        if not bb or len(bb) < 4:
            # sin bbox: fallback por longitud (título corto→center, largo→left)
            b["align"] = "center" if n_palabras <= 6 else "left"
            continue
        center_x = (bb[0] + bb[2]) / 2.0
        b["align"] = _normalizar_align(center_x, page_w, n_palabras)
    return layout


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("layout_json", nargs="+", type=Path)
    ap.add_argument("--write", action="store_true", help="escribe el layout de vuelta")
    args = ap.parse_args()

    for path in args.layout_json:
        data = json.loads(path.read_text(encoding="utf-8"))
        antes = [b.get("align") for b in data.get("blocks", [])]
        data = recalcular(data)
        despues = [b.get("align") for b in data.get("blocks", [])]
        if args.write:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{path.name}: aligns antes={antes.count('center')}c/{antes.count('left')}l "
              f"→ despues={despues.count('center')}c/{despues.count('left')}l/{despues.count('right')}r "
              f"({'escrito' if args.write else 'solo mostrado'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())