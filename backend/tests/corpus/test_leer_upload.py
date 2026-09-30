"""El tope de tamaño se aplica antes de leer el upload a memoria (F-02)."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, UploadFile

from src.adapters.http.upload import leer_upload, verificar_tamano_upload
from src.domain.services.validador_upload import MAX_BYTES


def _upload(size: int | None, contenido: bytes = b"%PDF-1.7") -> UploadFile:
    return UploadFile(file=io.BytesIO(contenido), size=size, filename="a.pdf")


async def test_rechaza_422_sin_leer_si_excede_el_tope() -> None:
    archivo = _upload(MAX_BYTES + 1)
    archivo.read = AsyncMock(return_value=b"")  # type: ignore[method-assign]

    with pytest.raises(HTTPException) as exc:
        await leer_upload(archivo)

    assert exc.value.status_code == 422
    archivo.read.assert_not_awaited()


async def test_lee_normalmente_si_no_excede() -> None:
    assert await leer_upload(_upload(8, b"%PDF-1.7")) == b"%PDF-1.7"


async def test_tamano_desconocido_se_deja_pasar_a_la_validacion_posterior() -> None:
    assert await leer_upload(_upload(None, b"%PDF")) == b"%PDF"


def test_verificar_tamano_upload_rechaza_el_excedido() -> None:
    with pytest.raises(HTTPException) as exc:
        verificar_tamano_upload(_upload(MAX_BYTES + 1))
    assert exc.value.status_code == 422
