"""Lectura de uploads con el tope de tamaño aplicado ANTES de cargarlos en memoria.

`ValidadorUpload` comprueba el tamaño sobre los bytes ya leidos; sin este
chequeo previo un archivo enorme se carga completo antes de rechazarse (F-02).
`UploadFile.size` lo fija Starlette al parsear el multipart.
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

from src.domain.services.validador_upload import (
    UploadInvalidoError,
    validar_size_declarado,
)


def verificar_tamano_upload(file: UploadFile) -> None:
    """422 si el tamano declarado excede el tope (tamano desconocido: pasa)."""
    try:
        validar_size_declarado(file.size)
    except UploadInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


async def leer_upload(file: UploadFile) -> bytes:
    """Lee el upload completo tras verificar su tamano declarado."""
    verificar_tamano_upload(file)
    return await file.read()
