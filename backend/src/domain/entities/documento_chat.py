"""Entidad de dominio DocumentoChat.

Regla Clean Architecture: dataclass pura, sin SQLAlchemy ni Pydantic.
El ORM vive en adapters/postgres/models/documento_chat.py.

Archivo adjunto a un mensaje del chat (PDF, docx, imagen, etc.). Sprint 4
solo modela la estructura; la extracción/indexación de estos documentos
es concerns de un sprint posterior si se requiere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

TipoDocumentoChat = Literal[
    "pdf",
    "doc",
    "docx",
    "txt",
    "md",
    "csv",
    "json",
    "png",
    "jpg",
    "jpeg",
    "bmp",
    "gif",
    "webp",
    "tiff",
]
EstadoProcesamiento = Literal["pendiente", "procesando", "completado", "fallido"]


@dataclass(slots=True)
class DocumentoChat:
    """Documento adjunto a un MensajeChat.

    Atributos:
        id: PK interno. None antes de persistir.
        chat_id: FK a chat_privado. Obligatorio.
        mensaje_id: FK a mensaje_chat. Obligatorio.
        usuario_id: FK a usuario. Quien subió el documento.
        nombre_original: Nombre del archivo al subirlo. CHECK length > 0.
        tamano_archivo: Bytes. CHECK > 0.
        tipo_documento: Uno de TipoDocumentoChat (CHECK en BD).
        estado_procesamiento: 'pendiente' | 'procesando' | 'completado' |
            'fallido'. Default 'pendiente'.
        uploaded_at: Timestamp de subida. None antes de persistir.
    """

    id: int | None
    chat_id: int
    mensaje_id: int
    usuario_id: int
    nombre_original: str
    tamano_archivo: int
    tipo_documento: TipoDocumentoChat
    estado_procesamiento: EstadoProcesamiento = "pendiente"
    uploaded_at: datetime | None = None
