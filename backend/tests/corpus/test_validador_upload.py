"""Tests unitarios de ValidadorUpload (Regla 3 Trail of Bits).

TDD: happy path + 4 casos inválidos (ext, CT, magic, size).
"""

from __future__ import annotations

import pytest

import src.domain.services.validador_upload as validador_upload
from src.domain.services.validador_upload import UploadInvalidoError, ValidadorUpload


def test_pdf_valido_con_magic():
    v = ValidadorUpload()
    data = b"%PDF-1.4\n%aaaaaa" + b"x" * 100
    v.validar("archivo.pdf", "application/pdf", data)  # no raise


def test_docx_valido_con_zip_magic():
    v = ValidadorUpload()
    data = b"PK\x03\x04xxxx" + b"y" * 100
    ct = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    v.validar("documento.docx", ct, data)  # no raise


def test_docx_valido_octet_stream():
    v = ValidadorUpload()
    v.validar("archivo.docx", "application/octet-stream", b"PK\x03\x04\x00\x00" + b"a" * 200)


def test_extension_no_permitida_rechazada():
    v = ValidadorUpload()
    with pytest.raises(UploadInvalidoError, match="exe"):
        v.validar("malware.exe", "application/octet-stream", b"\x00\x00")


def test_content_type_no_acorde_a_extension():
    v = ValidadorUpload()
    with pytest.raises(UploadInvalidoError, match="Content-Type.*no coincide.*pdf"):
        v.validar("norma.pdf", "image/png", b"%PDF-fake")


def test_magic_bytes_no_acorde_al_content_type():
    v = ValidadorUpload()
    with pytest.raises(UploadInvalidoError, match="Magic bytes"):
        v.validar("norma.pdf", "application/pdf", b"PK\x03\x04no-es-pdf")


def test_tamano_excede_500_mb(monkeypatch):
    """Exceder MAX_BYTES rechaza con error claro.

    Se achica MAX_BYTES via monkeypatch en vez de asignar 500 MiB reales:
    la asignacion bajo presion de memoria del worktree frio del gate
    superaba el timeout de pytest y colgaba la suite entera.
    """
    monkeypatch.setattr(validador_upload, "MAX_BYTES", 100)
    v = ValidadorUpload()
    data = b"%PDF" + b"x" * 101
    with pytest.raises(UploadInvalidoError, match="excede"):
        v.validar("grande.pdf", "application/pdf", data)


def test_nombre_vacio():
    v = ValidadorUpload()
    with pytest.raises(UploadInvalidoError, match="vacío"):
        v.validar("  ", "application/pdf", b"%PDF")


def test_nombre_con_path_traversal():
    v = ValidadorUpload()
    with pytest.raises(UploadInvalidoError, match="sospechoso"):
        v.validar("../etc/passwd", "application/pdf", b"%PDF")


def test_docx_octet_stream_sin_firma_zip_rechazado():
    """D-S2C-04: .docx como octet-stream sin cabecera PK se rechaza.

    Antes el magic se buscaba por Content-Type declarado y octet-stream
    no estaba en la tabla: la firma se saltaba. Ahora se exige por
    extensión, como promete la prosa ("revisa la firma antes de aceptar").
    """
    v = ValidadorUpload()
    with pytest.raises(UploadInvalidoError, match="Magic bytes"):
        v.validar("archivo.docx", "application/octet-stream", b"AAAA" + b"a" * 200)


def test_pdf_con_extension_docx_rechazado():
    """Contenido %PDF con extensión .docx se rechaza por firma."""
    v = ValidadorUpload()
    with pytest.raises(UploadInvalidoError, match="Magic bytes"):
        v.validar(
            "falso.docx",
            "application/octet-stream",
            b"%PDF-1.4" + b"x" * 100,
        )
