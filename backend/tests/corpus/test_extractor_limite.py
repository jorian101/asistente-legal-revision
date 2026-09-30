"""Tests del límite de tamaño del extractor (D-S2C-05).

El extractor construido sin tamaño usaba el default del adapter (50 MB)
mientras ValidadorUpload y Settings permiten 500 MB: un PDF de 60-500 MB
superaba la validación y moría en extracción con error contradictorio.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.ports.text_extractor import ExtractionMode, create_text_extractor


def test_factory_reenvia_max_size_bytes():
    ext = create_text_extractor(ExtractionMode.AUTO, max_size_bytes=123)
    assert ext.max_size_bytes == 123


def test_factory_sin_tamano_usa_default_adapter():
    from src.adapters.file_extractor import MAX_PDF_SIZE_DEFAULT

    ext = create_text_extractor(ExtractionMode.AUTO)
    assert ext.max_size_bytes == MAX_PDF_SIZE_DEFAULT


@pytest.mark.asyncio
async def test_extractor_rechaza_sobre_limite(tmp_path: Path):
    ext = create_text_extractor(ExtractionMode.AUTO, max_size_bytes=100)
    f = tmp_path / "grande.pdf"
    f.write_bytes(b"%PDF" + b"x" * 101)
    with pytest.raises(ValueError, match="excede l.mite"):
        await ext.extract(f)
