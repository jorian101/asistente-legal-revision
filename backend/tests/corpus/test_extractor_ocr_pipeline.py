"""Errores y calidad del pipeline OCR del extractor hibrido (F-25).

`subprocess.run` se sustituye por un doble: no se ejecuta el pipeline real.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.adapters import file_extractor
from src.adapters.file_extractor import HybridFileExtractor


def _ejecutar(monkeypatch, fake_run, tmp_path: Path):
    monkeypatch.setattr(file_extractor.subprocess, "run", fake_run)
    pdf = tmp_path / "escaneo.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    return HybridFileExtractor()._extract_via_ocr_pipeline(pdf)


def test_timeout_del_pipeline_es_un_error_claro(monkeypatch, tmp_path: Path) -> None:
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    with pytest.raises(RuntimeError, match="excedi"):
        _ejecutar(monkeypatch, fake_run, tmp_path)


def test_stderr_no_utf8_no_rompe_el_mensaje_de_error(monkeypatch, tmp_path: Path) -> None:
    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd, stderr=b"\xff\xfe fallo del motor")

    with pytest.raises(RuntimeError, match="OCR pipeline fall"):
        _ejecutar(monkeypatch, fake_run, tmp_path)


def test_bad_ratio_cuenta_cada_caracter_de_reemplazo_una_sola_vez(
    monkeypatch, tmp_path: Path
) -> None:
    texto = "a" * 98 + "��"  # 100 caracteres, 2 de reemplazo

    def fake_run(cmd, **kwargs):
        out = Path(cmd[cmd.index("--out") + 1]) / "doc"
        out.mkdir(parents=True)
        layout = {"blocks": [{"index": 0, "runs": [{"text": texto}]}], "meta": {"pages": 1}}
        (out / "layout.json").write_text(json.dumps(layout), encoding="utf-8")

    resultado = _ejecutar(monkeypatch, fake_run, tmp_path)

    assert resultado.metadata["bad_ratio"] == 0.02
    assert resultado.metadata["needs_review"] is True  # hay U+FFFD: sigue marcado
