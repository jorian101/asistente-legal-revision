"""Motor OCR #2 (PaddleOCR CPU) — corre como SUBPROCESO independiente.

Uso: uv run python -m formatos.extract_paddle <pdf> --out bloques-paddle.json

Al terminar y salir, el kernel libera toda su RAM (patrón proceso-por-motor).
Salida: [{"page": n, "lines": [{"text": str, "score": float}]}]
"""
from __future__ import annotations

import argparse
import json
import resource
import sys
from pathlib import Path


def _peak_mb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


def extraer_paddle(pdf: Path) -> list[dict]:
    import pymupdf
    from paddleocr import PaddleOCR

    # modelos mobile: ligeros en CPU (~decenas de MB)
    # enable_mkldnn=False: paddle 3.3 + onednn lanza NotImplementedError en infer
    ocr = PaddleOCR(
        lang="es",
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
    )
    paginas = []
    with pymupdf.open(pdf) as doc:
        for pno in range(doc.page_count):
            pix = doc[pno].get_pixmap(dpi=150)
            img = pdf.parent / f".paddle-page-{pno}.png"
            pix.save(img)
            try:
                res = ocr.predict(str(img))
            finally:
                img.unlink(missing_ok=True)
            lines = []
            for r in res:
                texts = r.get("rec_texts") or r.json.get("rec_texts", [])
                scores = r.get("rec_scores") or r.json.get("rec_scores", [])
                for t, s in zip(texts, scores):
                    t = t.strip()
                    if t:
                        lines.append({"text": t, "score": round(float(s), 3)})
            paginas.append({"page": pno + 1, "lines": lines})
    return paginas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    paginas = extraer_paddle(Path(args.pdf))
    out = {"pages": paginas, "engine": "paddleocr-mobile-cpu",
           "rss_peak_mb": _peak_mb()}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"paddle ok: {sum(len(p['lines']) for p in paginas)} líneas "
          f"(rss {out['rss_peak_mb']}MB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
