"""Layout extractor de alta fidelidad para obrados TSJM.

Router + extractores (docx nativo / pdf nativo / scan) -> layout.json +
vista.md editables. Ver plan: topic Engram formatos/tsjm-pipeline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from formatos.router import classify
from formatos.extract_docx import extract_docx
from formatos.extract_pdf_native import extract_pdf_native

try:
    from formatos.extract_scan import extract_scan
except ImportError:  # extras scan no instalados
    extract_scan = None

SLUG_MAX = 60


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:SLUG_MAX] or "sin-titulo"


def hash16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def apply_overrides(layout: dict, overrides_path: Path) -> int:
    """Aplica overrides.yaml simple: {blocks: {"pN:iM": {text?, align?, note?}}}."""
    if not overrides_path.exists():
        return 0
    try:
        import yaml

        ov = yaml.safe_load(overrides_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - override roto no debe frenar extracción
        print(f"  aviso: overrides.yaml ilegible ({exc}); se ignora", file=sys.stderr)
        return 0
    applied = 0
    for key, patch in (ov.get("blocks") or {}).items():
        m = re.fullmatch(r"p(\d+):i(\d+)", str(key))
        if not m:
            continue
        page, idx = int(m.group(1)), int(m.group(2))
        for b in layout["blocks"]:
            if b["page"] == page and b.get("index") == idx:
                if "text" in patch and b.get("runs"):
                    b["runs"][0]["text"] = str(patch["text"])
                    b["runs"][0]["overridden"] = True
                if "align" in patch:
                    b["align"] = patch["align"]
                if "note" in patch:
                    b["note"] = patch["note"]
                b["overridden"] = True
                applied += 1
    if applied:
        layout["meta"]["overrides_aplicados"] = applied
    return applied


def render_vista(layout: dict, out_md: Path) -> None:
    m = layout["meta"]
    lines = [
        f"# Vista — {Path(m['source_file']).name}",
        "",
        f"> tipo: `{m['tipo']}` · autor: `{m['autor']}` · motor: `{m['engine']}` · "
        f"páginas: {m['pages']} · bloques: {len(layout['blocks'])}",
        f"> fuente: {m['source_file']}",
        "> Editar correcciones en `overrides.yaml` (clave `p<page>:i<index>`);",
        "> NO editar `layout.json` a mano (se regenera).",
        "",
    ]
    cur_page = None
    for b in layout["blocks"]:
        if b["page"] != cur_page:
            cur_page = b["page"]
            lines += ["", f"## Página {cur_page}", ""]
        tags = [f"`p{b['page']}:i{b.get('index')}`", f"[{b['align'].upper()}]"]
        if b.get("kind") == "table":
            tags.append("[TABLA]")
        text_parts = []
        for r in b.get("runs", []):
            t = r["text"]
            if r.get("bold"):
                t = f"**{t}**"
            if r.get("italic"):
                t = f"*{t}*"
            text_parts.append(t)
        text = " ".join(text_parts)
        if len(text) > 300:
            text = text[:300] + "…"
        lines.append(f"- {' '.join(tags)} {text}")
        lines.append("")
    out_md.write_text("\n".join(lines), encoding="utf-8")


def append_manifest(manifest: Path, row: dict) -> None:
    header = (
        "# Manifiesto de formatos extraídos\n\n"
        "| documento | tipo | autor | motor | páginas | bloques | hash16 |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    if not manifest.exists():
        manifest.write_text(header, encoding="utf-8")
    manifest.open("a", encoding="utf-8").write(
        f"| {row['doc']} | {row['tipo']} | {row['autor']} | {row['engine']} "
        f"| {row['pages']} | {row['blocks']} | {row['hash16']} |\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inputs", nargs="+", help="archivos o directorios a procesar")
    ap.add_argument("--out", required=True, help="raíz del vault sources/formatos")
    ap.add_argument("--tipo", default="otro", help="TipoDocumento de obra.py")
    ap.add_argument("--autor", default="desconocido",
                    help="aliaga | tsjm-otro | instancia-inferior | parte | desconocido")
    ap.add_argument("--sin-consenso", action="store_true",
                    help="scans: omite la segunda opinión de PaddleOCR")
    args = ap.parse_args()

    files: list[Path] = []
    for raw in args.inputs:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(x for x in p.iterdir() if x.suffix.lower() in {".pdf", ".docx"}))
        else:
            files.append(p)

    out_root = Path(args.out)
    manifest = out_root / "manifiesto-formatos.md"

    for f in files:
        kind = classify(f)
        print(f"{f.name}: {kind}")
        if kind == "unsupported":
            continue
        if kind == "docx":
            layout = extract_docx(f)
        elif kind == "native-pdf":
            layout = extract_pdf_native(f)
        elif kind == "scan":
            if extract_scan is None:
                print("  -> escaneado: instalar extra `scan` (docling) para rama OCR")
                continue
            layout = extract_scan(f)
            # motor 2 (paddle) como subproceso; fallo NO bloquea la extracción
            if args.sin_consenso is False:
                try:
                    with tempfile.NamedTemporaryFile(suffix=".json",
                                                     delete=False) as tmp:
                        tmp_path = Path(tmp.name)
                    subprocess.run(
                        [sys.executable, "-m", "formatos.extract_paddle",
                         str(f), "--out", str(tmp_path)],
                        check=True, capture_output=True, timeout=1800,
                    )
                    from formatos.consenso import aplicar_consenso
                    paddle_json = json.loads(tmp_path.read_text(encoding="utf-8"))
                    n_rev = aplicar_consenso(layout, paddle_json)
                    print(f"  consenso paddle: {n_rev} bloques a revisión")
                except Exception as exc:  # noqa: BLE001
                    print(f"  aviso consenso paddle falló ({exc}); "
                          "se conserva solo docling", file=sys.stderr)
                finally:
                    tmp_path.unlink(missing_ok=True)
        else:
            continue
        layout["meta"]["tipo"] = args.tipo
        layout["meta"]["autor"] = args.autor

        doc_dir = out_root / args.tipo / slugify(f.stem.lower())
        doc_dir.mkdir(parents=True, exist_ok=True)
        applied = apply_overrides(layout, doc_dir / "overrides.yaml")
        (doc_dir / "layout.json").write_text(
            json.dumps(layout, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        render_vista(layout, doc_dir / "vista.md")
        row = {
            "doc": doc_dir.relative_to(out_root).as_posix(),
            "tipo": args.tipo,
            "autor": args.autor,
            "engine": layout["meta"]["engine"],
            "pages": layout["meta"]["pages"],
            "blocks": len(layout["blocks"]),
            "hash16": hash16(f),
        }
        append_manifest(manifest, row)
        print(f"  ok {doc_dir} (bloques={row['blocks']}, overrides={applied})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
