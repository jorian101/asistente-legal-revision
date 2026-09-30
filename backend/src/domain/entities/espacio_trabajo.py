"""Entidad de dominio EspacioTrabajo.

Regla Clean Architecture: dataclass pura, sin SQLAlchemy ni Pydantic.
El ORM vive en adapters/postgres/models/espacio_trabajo.py.

Carpeta del sidebar del Asistente dentro de un expediente. Reemplaza la
noción de "folder" del chatStore localStorage (Sprint 4 Opción B #133).
Tipos: 'fijado' (pinned), 'archivado', 'personalizado' (custom del user).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

TipoEspacio = Literal["fijado", "archivado", "personalizado"]
EstadoEspacio = Literal["activo", "eliminado"]


@dataclass(slots=True)
class EspacioTrabajo:
    """Carpeta de chats dentro de un expediente.

    Atributos:
        id: PK interno. None antes de persistir.
        expediente_id: FK a expediente. Obligatorio.
        propietario_id: FK a usuario. Quien creó la carpeta.
        nombre: Visible en el sidebar. CHECK length > 0.
        tipo: 'fijado' | 'archivado' | 'personalizado'. Default este último.
        estado: 'activo' | 'eliminado'. Default 'activo'.
        created_at: Timestamp de creación. None antes de persistir.
        updated_at: Timestamp de edición. None si nunca.
    """

    id: int | None
    expediente_id: int
    propietario_id: int
    nombre: str
    tipo: TipoEspacio = "personalizado"
    estado: EstadoEspacio = "activo"
    created_at: datetime | None = None
    updated_at: datetime | None = None
