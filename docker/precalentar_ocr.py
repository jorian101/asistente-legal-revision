"""Corre una vez el OCR de escaneos al construir la imagen para dejar los modelos en caché.

Docling baja sus modelos la primera vez que convierte; en la máquina del usuario no hay
internet (HF_HUB_OFFLINE=1), así que se descargan acá. Falla el build si el OCR no anda.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import fitz  # pymupdf

with tempfile.TemporaryDirectory() as tmp:
    # PDF "escaneado": una página que es solo imagen, sin capa de texto.
    texto = fitz.open()
    texto.new_page().insert_text((72, 100), "AUTO DE VISTA. Se declara procedente.", fontsize=18)
    imagen = texto[0].get_pixmap(dpi=150)
    escaneo = fitz.open()
    escaneo.new_page().insert_image(fitz.Rect(0, 0, 612, 792), pixmap=imagen)
    pdf = Path(tmp) / "escaneo.pdf"
    escaneo.save(pdf)

    subprocess.run(
        [sys.executable, "-m", "formatos.cli", str(pdf), "--out", f"{tmp}/out",
         "--tipo", "otro", "--autor", "desconocido", "--sin-consenso"],
        cwd="/app/tools/formatos",
        check=True,
    )
    print("OCR precalentado:", sorted(p.name for p in Path(tmp, "out").rglob("*"))[:5])
