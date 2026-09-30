"""Clasifica un archivo: docx | native-pdf | scan | unsupported."""
from __future__ import annotations

from pathlib import Path


def classify(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".docx":
        return "docx"
    if ext != ".pdf":
        return "unsupported"
    try:
        import pymupdf

        with pymupdf.open(path) as doc:
            if doc.is_encrypted:
                return "unsupported"
            sample = min(3, doc.page_count)
            chars = sum(len(doc[i].get_text("text").strip()) for i in range(sample))
            avg = chars / max(sample, 1)
        return "native-pdf" if avg >= 40 else "scan"
    except Exception as exc:  # noqa: BLE001
        print(f"  aviso router {path.name}: {exc}")
        return "unsupported"
