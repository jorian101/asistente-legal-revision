"""Protocolo de extracción de texto (TextExtractor).

Define la interfaz que deben implementar los adapters de extracción PDF/Word.
Regla Clean Architecture: el dominio/aplicación depende de este protocolo,
NO de la implementación concreta (PyMuPDF, python-docx, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class TextBlock:
    """Bloque de texto con coordenadas físicas (modo raw)."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    block_no: int
    block_type: int  # 0 = texto, 1 = imagen (per fitz)


@dataclass(slots=True, frozen=True)
class ExtractionResult:
    """Resultado de extracción de un rango de páginas."""

    full_text: str  # Texto completo concatenado
    blocks: list[TextBlock]  # Bloques con coords (solo modo raw)
    pages_count: int  # Total páginas en el documento
    extracted_pages: list[int]  # Páginas que se extrajeron (1-indexed)
    metadata: dict  # Metadatos del PDF (autor, título, etc.)


class TextExtractor(ABC):
    """Interfaz para extractores de texto de documentos."""

    @abstractmethod
    async def extract(
        self,
        file_path: Path,
        pages: list[int] | None = None,
    ) -> ExtractionResult:
        """Extrae texto del documento.

        Args:
            file_path: Ruta al archivo (PDF o DOCX).
            pages: Lista de números de página 1-indexed a extraer.
                   None = todas las páginas.

        Returns:
            ExtractionResult con texto, bloques (si raw) y metadatos.

        Raises:
            FileNotFoundError: Si el archivo no existe.
            ValueError: Si el formato no es soportado o magia inválida.
        """
        ...

    @abstractmethod
    async def extract_pages(
        self,
        file_path: Path,
        pages: list[int],
    ) -> ExtractionResult:
        """Alias explícito para extraer páginas específicas (1-indexed)."""
        ...


# --- Factory para Composition Root ---


class ExtractionMode:
    RAW = "raw"  # fitz.get_text("blocks") — coords físicas
    MARKDOWN = "markdown"  # pymupdf4llm.to_markdown() — estructura lógica
    AUTO = "auto"  # híbrido: docx + pdf nativo + scan OCR (recomendado para CargarObra)


def create_text_extractor(
    mode: str = ExtractionMode.RAW, max_size_bytes: int | None = None
) -> TextExtractor:
    """Factory del extractor según modo.

    Args:
        mode: "raw" (fitz blocks), "markdown" (pymupdf4llm) o "auto" (híbrido).
        max_size_bytes: límite de tamaño aplicado por el extractor. Si es None
            se usa el default del adapter (50 MB); en runtime se pasa
            `Settings.max_pdf_size_bytes` (500 MB, consistente con el validador).

    Returns:
        Instancia de TextExtractor configurada.

    Note:
        La importación perezosa evita dependencias circulares y permite
        que tests mockeen sin cargar PyMuPDF.
    """
    kwargs = {} if max_size_bytes is None else {"max_size_bytes": max_size_bytes}
    if mode == ExtractionMode.RAW:
        from src.adapters.file_extractor import PyMuPdfRawExtractor

        return PyMuPdfRawExtractor(**kwargs)
    elif mode == ExtractionMode.MARKDOWN:
        from src.adapters.file_extractor import PyMuPdfMarkdownExtractor

        return PyMuPdfMarkdownExtractor(**kwargs)
    elif mode == ExtractionMode.AUTO:
        from src.adapters.file_extractor import HybridFileExtractor

        return HybridFileExtractor(**kwargs)
    else:
        raise ValueError(f"Modo de extracción desconocido: {mode}. Use 'raw', 'markdown' o 'auto'")
