"""Servicio de dominio: ValidadorUpload — Regla 3 Trail of Bits.

Cadena de validación de upload de archivos al corpus (en este orden):
1. Nombre no vacío y sin path traversal
2. Extensiones permitidas (.pdf, .docx)
3. Content-Type declarado vs extensión
4. Magic bytes (firma real del archivo) vs extensión
5. Tamaño <= 500 MB

Aislado del HTTP: no usa UploadFile ni FastAPI. Solo bytes + strings.
Testeable sin levantar servidor.
"""

from __future__ import annotations

from pathlib import PurePosixPath

# Extensiones permitidas
_EXT_PERMITIDAS = frozenset({".pdf", ".docx"})
# Magic bytes por extension (la firma se exige por extension, no por el
# Content-Type declarado: un .docx enviado como octet-stream tambien
# debe traer su firma PK, igual que un .pdf trae %PDF)
_MAGIC_POR_EXT = {
    ".pdf": b"%PDF",
    ".docx": b"PK\x03\x04",
}
# Mapeo extensión -> Content-Types aceptados (flexibles: aplication/pdf, etc.)
_EXT_A_CT = {
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    },
}

MAX_BYTES = 500 * 1024 * 1024  # 500 MB (consistente con .env.example y Settings)


class UploadInvalidoError(ValueError):
    """Upload falló alguna validación de la Regla 3."""


def validar_size_declarado(size: int | None) -> None:
    """Rechaza un tamano que excede MAX_BYTES (None = desconocido: no rechaza)."""
    if size is not None and size > MAX_BYTES:
        raise UploadInvalidoError(
            f"Archivo de {size} bytes excede el máximo de {MAX_BYTES} bytes (500 MB)."
        )


class ValidadorUpload:
    """Valida uploads de documentos jurídicos (Regla 3 Trail of Bits)."""

    def validar(self, filename: str, content_type: str, data: bytes) -> None:
        """Ejecuta la cadena. Raises UploadInvalidoError con motivo si falla."""
        self._validar_filename(filename)
        ext = self._validar_extension(filename)
        self._validar_content_type(content_type, ext)
        self._validar_magic(data, ext)
        self._validar_size(data)

    # ----- pasos -------------------------------------------------------

    def _validar_filename(self, filename: str) -> None:
        if not filename or not filename.strip():
            raise UploadInvalidoError("Nombre de archivo vacío.")
        # Path traversal: reject .. y / y \ absolutos
        if ".." in filename or filename.startswith(("/", "\\")):
            raise UploadInvalidoError("Nombre de archivo con path sospechoso.")

    def _validar_extension(self, filename: str) -> str:
        ext = PurePosixPath(filename).suffix.lower()
        if ext not in _EXT_PERMITIDAS:
            raise UploadInvalidoError(
                f"Extensión '{ext}' no permitida. Permitidas: {sorted(_EXT_PERMITIDAS)}."
            )
        return ext

    def _validar_content_type(self, content_type: str, ext: str) -> None:
        ct = (content_type or "").lower().strip()
        aceptados = _EXT_A_CT.get(ext, set())
        if ct not in aceptados:
            raise UploadInvalidoError(
                f"Content-Type '{ct}' no coincide con extensión '{ext}'. "
                f"Aceptados: {sorted(aceptados)}."
            )

    def _validar_magic(self, data: bytes, ext: str) -> None:
        esperado = _MAGIC_POR_EXT[ext]
        if not data.startswith(esperado):
            raise UploadInvalidoError(
                f"Magic bytes no coinciden con extensión '{ext}'. "
                f"Se esperaba firma {esperado!r} al inicio del archivo."
            )

    def _validar_size(self, data: bytes) -> None:
        validar_size_declarado(len(data))
