"""Entidad de dominio MensajeChat.

Regla Clean Architecture: dataclass pura, sin SQLAlchemy ni Pydantic.
El ORM vive en adapters/postgres/models/mensaje_chat.py.

Mensaje individual dentro de un ChatPrivado. Tipo 'user' o 'bot'
(respuesta del pipeline RAG). Sprint 6 extenderá el contenido del bot
con la generación del LLM; Sprint 4 modela la estructura.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

TipoMensaje = Literal["user", "bot"]
EstadoMensaje = Literal["activo", "editado", "eliminado"]


@dataclass(slots=True)
class MensajeChat:
    """Mensaje de un chat (turno user o bot).

    Atributos:
        id: PK interno. None antes de persistir.
        chat_id: FK a chat_privado. Obligatorio.
        usuario_id: FK a usuario. Emisor del mensaje (en bot, usuario
            que disparó la consulta).
        tipo: 'user' | 'bot'.
        contenido: Texto del mensaje. CHECK length > 0.
        razonamiento: Cadena vacía por defecto. Reservado para el
            chain-of-thought del LLM (Sprint 6).
        estado: 'activo' | 'editado' | 'eliminado'. Default 'activo'.
        posicion: Orden del mensaje dentro del chat. CHECK unique entre
            visibles (activo/editado) por chat.
        metadatos: JSONB opcional (contexto recuperado, latencia, etc.).
        created_at: Timestamp de creación. None antes de persistir.
        updated_at: Timestamp de edición. None si nunca.
    """

    id: int | None
    chat_id: int
    usuario_id: int
    tipo: TipoMensaje
    contenido: str
    posicion: int
    razonamiento: str = ""
    estado: EstadoMensaje = "activo"
    metadatos: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
