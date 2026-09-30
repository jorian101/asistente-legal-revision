"""El PDF nativo se parsea en un subproceso aislado, no en la API (R5 / F-08).

Un PDF malicioso o corrupto que tumbe la libreria nativa de PyMuPDF debe matar
solo al worker; la API recibe un error controlado (que CargarObra mapea a 422).
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz
import pytest

from src.adapters import file_extractor
from src.adapters.file_extractor import HybridFileExtractor

TEXTO = "Texto de prueba para el extractor aislado. " * 6


def _pdf(ruta: Path, texto: str | None = TEXTO, **guardar) -> Path:
    doc = fitz.Document()  # no usa fitz.open, que el fixture prohibe en el proceso principal
    pagina = doc.new_page()
    if texto:
        pagina.insert_text((72, 72), texto)
    doc.save(ruta, **guardar)
    doc.close()
    return ruta


@pytest.fixture
def parent_sin_fitz(monkeypatch):
    """Falla si el proceso de la API abre un PDF con fitz: debe hacerlo el worker."""

    def _prohibido(*args, **kwargs):
        raise AssertionError("fitz.open se ejecuto en el proceso principal")

    monkeypatch.setattr(file_extractor.fitz, "open", _prohibido)


@pytest.mark.asyncio
async def test_pdf_valido_se_extrae_en_el_worker(parent_sin_fitz, tmp_path: Path) -> None:
    resultado = await HybridFileExtractor().extract(_pdf(tmp_path / "ok.pdf"))

    assert "Texto de prueba" in resultado.full_text
    assert resultado.pages_count == 1
    assert resultado.blocks and resultado.blocks[0].text
    assert resultado.metadata["is_pdf"] is True


@pytest.mark.asyncio
async def test_pdf_corrupto_es_un_error_controlado(parent_sin_fitz, tmp_path: Path) -> None:
    corrupto = tmp_path / "corrupto.pdf"
    corrupto.write_bytes(b"%PDF-1.7\n" + b"\x00\xff basura " * 50)

    with pytest.raises(RuntimeError):
        await HybridFileExtractor().extract(corrupto)


@pytest.mark.asyncio
async def test_pdf_cifrado_se_rechaza_con_valueerror(parent_sin_fitz, tmp_path: Path) -> None:
    cifrado = _pdf(
        tmp_path / "cifrado.pdf",
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="dueno",
        user_pw="usuario",
    )

    with pytest.raises(ValueError, match="encriptado"):
        await HybridFileExtractor().extract(cifrado)


@pytest.mark.asyncio
async def test_pdf_sin_texto_se_deriva_al_pipeline_ocr(
    parent_sin_fitz, monkeypatch, tmp_path: Path
) -> None:
    llamado: list[Path] = []
    sentinela = object()

    def _fake_ocr(self, ruta):
        llamado.append(ruta)
        return sentinela

    monkeypatch.setattr(HybridFileExtractor, "_extract_via_ocr_pipeline", _fake_ocr)

    resultado = await HybridFileExtractor().extract(_pdf(tmp_path / "escaneo.pdf", texto=None))

    assert resultado is sentinela
    assert llamado == [tmp_path / "escaneo.pdf"]


@pytest.mark.asyncio
async def test_si_el_worker_muere_la_api_sigue_viva(
    parent_sin_fitz, monkeypatch, tmp_path: Path
) -> None:
    ruta = _pdf(tmp_path / "ok.pdf")
    real = file_extractor._comando_worker
    monkeypatch.setattr(
        file_extractor,
        "_comando_worker",
        lambda *a, **k: [sys.executable, "-c", "import os; os._exit(139)"],  # como un segfault
    )

    with pytest.raises(RuntimeError, match="worker"):
        await HybridFileExtractor().extract(ruta)

    # El proceso de pytest (la "API") sigue vivo y una extraccion posterior funciona.
    monkeypatch.setattr(file_extractor, "_comando_worker", real)
    resultado = await HybridFileExtractor().extract(ruta)
    assert "Texto de prueba" in resultado.full_text


@pytest.mark.asyncio
async def test_worker_que_se_cuelga_se_mata_por_timeout(
    parent_sin_fitz, monkeypatch, tmp_path: Path
) -> None:
    ruta = _pdf(tmp_path / "ok.pdf")
    monkeypatch.setattr(file_extractor, "_PDF_WORKER_TIMEOUT_S", 0.5)
    monkeypatch.setattr(
        file_extractor,
        "_comando_worker",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(30)"],
    )

    with pytest.raises(RuntimeError, match="tiempo"):
        await HybridFileExtractor().extract(ruta)
