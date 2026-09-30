"""Extractor PDF escaneado -> layout dict vía Docling (layout) + Tesseract spa.

Consenso: este es el motor base. PaddleOCR (ocr2) y Marker fast (marker)
corren como pasadas separadas por proceso y se comparan en F2+.
"""
from __future__ import annotations

import resource
from datetime import datetime
from pathlib import Path


def _peak_mb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


def extract_scan(path: Path) -> dict:
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TesseractCliOcrOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = True
    # CLI: usa el tesseract 5.3.4-spa del sistema (sin binding extra)
    opts.ocr_options = TesseractCliOcrOptions(lang=["spa"])
    converter = DocumentConverter(
        format_options={"application/pdf": PdfFormatOption(pipeline_options=opts)}
    )
    result = converter.convert(str(path))
    doc = result.document

    blocks_out: list[dict] = []
    idx = 0
    n_pictures = 0
    for item, _level in doc.iterate_items():
        if item.label == "picture":
            n_pictures += 1
            continue
        if item.label not in {"text", "section_header", "title",
                              "list_item", "caption"}:
            continue
        text = (getattr(item, "text", "") or "").strip()
        if not text:
            continue
        bbox = None
        page_no = 1
        prov = getattr(item, "prov", None) or []
        if prov:
            p0 = prov[0]
            bbox = [round(getattr(p0.bbox, "l", 0), 1),
                    round(getattr(p0.bbox, "t", 0), 1),
                    round(getattr(p0.bbox, "r", 0), 1),
                    round(getattr(p0.bbox, "b", 0), 1)]
            page_no = getattr(p0, "page_no", 1) or 1
        kind = "heading" if item.label in {"section_header", "title"} else "paragraph"
        blocks_out.append({
            "kind": kind,
            "page": page_no,
            "index": idx,
            "bbox": bbox,
            "align": "left",
            "confidence": 0.8,
            "runs": [{"text": text, "bold": False, "italic": False,
                      "underline": False,
                      "allcaps": text.isupper() and len(text) > 2,
                      "size_pt": None, "font": None}],
        })
        idx += 1

    meta = {
        "source_file": str(path),
        "engine": "docling+tess-cli-spa (auto puede usar rapidocr/pp-ocrv6)",
        "pages": doc.num_pages(),
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "page": {},
        "nota": "scan: OCR + layout Docling; estilos carácter NO confiables en "
                "scans (v1); consenso con paddle/marker pendiente",
        "pictures": n_pictures,
        "rss_peak_mb": _peak_mb(),
    }
    return {"meta": meta, "blocks": blocks_out}
