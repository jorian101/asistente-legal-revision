"""Extractor PDF nativo -> layout dict (PyMuPDF: bbox, fuente, tamaño, flags)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pymupdf

BOLD_BIT, ITALIC_BIT = 16, 2


def _align_of(block_bbox: tuple, lines_widths: list[float], page_w: float,
              primer_texto: str = "") -> str:
    x0, _, x1, _ = block_bbox
    center_off = abs((x0 + x1) / 2 - page_w / 2)
    width_ratio = (x1 - x0) / page_w
    # "centrado por espacios": encabezados con sangría grande de espacios
    # (herencia de Word) — el texto real empieza muy adentro del bloque.
    if primer_texto:
        lead = len(primer_texto) - len(primer_texto.lstrip(" "))
        if lead >= 4 and width_ratio < 0.85:
            return "center"
    if lines_widths and max(lines_widths) / max(min(lines_widths), 1) < 1.15:
        # líneas de ancho parejo: centrado si el bloque está al medio y no ocupa todo
        if center_off < page_w * 0.05 and width_ratio < 0.85:
            return "center"
    if x0 > page_w * 0.55 and center_off < page_w * 0.08:
        return "right"
    return "left"


def extract_pdf_native(path: Path) -> dict:
    blocks_out: list[dict] = []
    idx = 0
    with pymupdf.open(path) as doc:
        meta_pages = {
            "width_pt": round(doc[0].rect.width, 1),
            "height_pt": round(doc[0].rect.height, 1),
        }
        for pno in range(doc.page_count):
            page = doc[pno]
            for b in page.get_text("dict", sort=True)["blocks"]:
                if b.get("type") != 0:  # 0=texto; imágenes se listan aparte en F2+
                    continue
                runs, widths = [], []
                for ln in b["lines"]:
                    for sp in ln["spans"]:
                        txt = sp["text"]
                        if not txt.strip():
                            continue
                        runs.append({
                            "text": txt,
                            "bold": bool(sp["flags"] & BOLD_BIT),
                            "italic": bool(sp["flags"] & ITALIC_BIT),
                            "underline": False,
                            "allcaps": txt.isupper() and len(txt.strip()) > 2,
                            "size_pt": round(sp["size"], 1),
                            "font": sp["font"],
                            "bbox": [round(v, 1) for v in sp["bbox"]],
                        })
                    widths.append(ln["bbox"][2] - ln["bbox"][0])
                if not runs:
                    continue
                size_mode = max((r["size_pt"] for r in runs), default=None)
                primero = runs[0]["text"] if runs else ""
                blocks_out.append({
                    "kind": "paragraph",
                    "page": pno + 1,
                    "index": idx,
                    "bbox": [round(v, 1) for v in b["bbox"]],
                    "align": _align_of(b["bbox"], widths, page.rect.width,
                                       primero),
                    "size_pt_mode": size_mode,
                    "confidence": 0.95,
                    "runs": runs,
                })
                idx += 1

    meta = {
        "source_file": str(path),
        "engine": "pymupdf",
        "pages": len(blocks_out) and (blocks_out[-1]["page"]) or 1,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "page": meta_pages,
        "nota": "pdf nativo: posiciones exactas; subrayado no expuesto por PyMuPDF (v1)",
    }
    return {"meta": meta, "blocks": blocks_out}
