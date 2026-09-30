"""Extractor .docx nativo -> layout dict (estilos exactos vía python-docx)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.table import Table
from docx.text.paragraph import Paragraph

_ALIGN = {
    WD_ALIGN_PARAGRAPH.CENTER: "center",
    WD_ALIGN_PARAGRAPH.RIGHT: "right",
    WD_ALIGN_PARAGRAPH.JUSTIFY: "justify",
}


def _runs(p: Paragraph) -> list[dict]:
    out = []
    for r in p.runs:
        if not r.text:
            continue
        size = r.font.size.pt if r.font.size else None
        out.append({
            "text": r.text,
            "bold": bool(r.bold),
            "italic": bool(r.italic),
            "underline": bool(r.underline),
            "allcaps": r.text.isupper() and len(r.text.strip()) > 2,
            "size_pt": round(size, 1) if size else None,
            "font": r.font.name,
        })
    return out


def _pf(p: Paragraph) -> dict:
    pf = p.paragraph_format

    def pt(v):
        return round(v.pt, 1) if v is not None else None

    return {
        "indent_first_line_pt": pt(pf.first_line_indent),
        "left_indent_pt": pt(pf.left_indent),
        "space_before_pt": pt(pf.space_before),
        "space_after_pt": pt(pf.space_after),
        "line_spacing": pf.line_spacing,
    }


def _para_block(p: Paragraph, index: int) -> dict | None:
    runs = _runs(p)
    text = "".join(r["text"] for r in runs).strip()
    style = p.style.name if p.style is not None and p.style.name != "Normal" else None
    if not text and not style:
        return None
    align = _ALIGN.get(p.alignment, "left")
    block = {
        "kind": "heading" if (style or "").lower().startswith(("heading", "tít")) else "paragraph",
        "page": 1,
        "index": index,
        "bbox": None,
        "align": align,
        "style": style,
        **_pf(p),
        "confidence": 1.0,
        "runs": runs or [{"text": "", "bold": False, "italic": False,
                          "underline": False, "allcaps": False,
                          "size_pt": None, "font": None}],
    }
    return block


def extract_docx(path: Path) -> dict:
    d = docx.Document(str(path))
    blocks: list[dict] = []
    idx = 0
    for child in d.element.body.iterchildren():
        if child.tag.endswith("}p"):
            b = _para_block(Paragraph(child, d), idx)
            if b:
                blocks.append(b)
                idx += 1
        elif child.tag.endswith("}tbl"):
            t = Table(child, d)
            rows = [[c.text.strip() for c in row.cells] for row in t.rows]
            blocks.append({"kind": "table", "page": 1, "index": idx, "bbox": None,
                           "align": "left", "rows": rows, "confidence": 1.0,
                           "runs": []})
            idx += 1

    sec = d.sections[0]
    meta = {
        "source_file": str(path),
        "engine": "python-docx",
        "pages": None,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "page": {
            "width_mm": round(sec.page_width.mm, 1),
            "height_mm": round(sec.page_height.mm, 1),
            "margin_left_mm": round(sec.left_margin.mm, 1),
            "margin_right_mm": round(sec.right_margin.mm, 1),
            "margin_top_mm": round(sec.top_margin.mm, 1),
            "margin_bottom_mm": round(sec.bottom_margin.mm, 1),
        },
        "nota": "docx nativo: estilos exactos; paginación física depende de render",
    }
    return {"meta": meta, "blocks": blocks}
