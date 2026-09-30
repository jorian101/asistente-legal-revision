"""Value object: RegistroAuditoria — entrada de la auditoria (Trail of Bits R6).

Representa una accion sensitiva registrada en audit_log. Pure VO: no depende
de infra. El use case RegistrarAuditoria lo persiste via AuditLogRepo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class RegistroAuditoria:
    """Un registro de auditoria (append-only).

    Atributos:
        accion: Verbo de la accion sensitiva (ej. 'login', 'crear_expediente',
            'publicar_borrador', 'indexar_norma').
        usuario_id: ID del usuario que ejecuto la accion. None para acciones
            de sistema (ej. login fallido sin usuario resuelto).
        entidad: Tipo de entidad afectada (ej. 'expediente', 'borrador').
            None si no aplica (ej. login).
        entidad_id: ID de la entidad afectada. None si no aplica.
        detalle: Contexto adicional (ip, carnet, extra). Opcional.
        created_at: Momento del registro. None = server_default NOW().
    """

    accion: str
    usuario_id: int | None
    entidad: str | None = None
    entidad_id: int | None = None
    detalle: dict[str, Any] | None = None
    created_at: datetime | None = None
