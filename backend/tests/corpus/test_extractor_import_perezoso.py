"""Importar file_extractor no debe cargar pymupdf4llm/onnxruntime (F-08).

El comentario decia "se importa perezoso" pero el try-import era eager: cada
import (y cada subproceso worker) pagaba ~1 s y ~100 MB de onnxruntime. Se
comprueba en un interprete limpio porque tests/conftest.py precarga pymupdf4llm.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def test_importar_file_extractor_no_carga_pymupdf4llm() -> None:
    codigo = "import sys; import src.adapters.file_extractor; print('pymupdf4llm' in sys.modules)"

    salida = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout.strip()

    assert salida == "False"
