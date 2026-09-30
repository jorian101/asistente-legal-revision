"""Entidad de dominio ChatPrivado.

Regla Clean Architecture: dataclass pura, sin SQLAlchemy ni Pydantic.
El ORM vive en adapters/postgres/models/chat_privado.py.

Conversación RAG persistente, opcionalmente atada a un expediente (None =
chat general sobre el corpus vectorial). Sprint 4 (Opción B
del fork #133) la usa como fuente de verdad del sidebar del Asistente,
reemplazando el chatStore localStorage. `consulta_historial` sigue como
log inmutable de auditoría/KPIs (separation of concerns).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

EstadoChat = Literal["activo", "archivado", "eliminado"]
PrioridadChat = Literal["baja", "media", "alta", "critica"]
ContextoLegal = Literal[
    "caso_legal",
    "audiencia",
    "reunion",
    "antecedente",
    "documento_legal",
    "consulta_general",
]


@dataclass(slots=True)
class ChatPrivado:
    """Conversación persistente, opcionalmente atada a un expediente.

    Atributos:
        id: PK interno. None antes de persistir.
        expediente_id: FK a expediente. None para chats generales que se
            basan solo en el corpus vectorial (migración b7c8d9e0f1a2
            relajó el NOT NULL original de 8f345a460a82).
        espacio_trabajo_id: FK opcional a espacio_trabajo (carpeta del chat).
        propietario_id: FK a usuario. Quien creó el chat.
        titulo: Título visible en el sidebar. CHECK length > 0.
        estado: 'activo' | 'archivado' | 'eliminado'. Default 'activo'.
        prioridad: 'baja' | 'media' | 'alta' | 'critica'. Default 'media'.
        contexto_legal: Clasificación del contexto. None si no aplica.
        created_at: Timestamp de creación. None antes de persistir.
        updated_at: Timestamp de últimaActualización. None si nunca.
        ultimo_mensaje_at: Timestamp del último mensaje. None si vacío.
    """

    id: int | None
    expediente_id: int | None
    propietario_id: int
    titulo: str
    espacio_trabajo_id: int | None = None
    estado: EstadoChat = "activo"
    prioridad: PrioridadChat = "media"
    contexto_legal: ContextoLegal | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    ultimo_mensaje_at: datetime | None = None
