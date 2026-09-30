"""Entidad de dominio Expediente.

Regla Clean Architecture: dataclass pura, sin SQLAlchemy ni Pydantic.
El ORM vive en adapters/postgres/models/expediente.py y mapea esta entidad
a la tabla `expediente`.

El expediente es el caso procesal del TSJM (Tribunal Supremo de Justicia
Militar). Un expediente agrupa obras (piezas procesales) y es el eje
central sobre el que pivotan consultas, borradores e historial.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

TipoProceso = Literal["consulta", "apelacion_incidental", "apelacion_restringida"]
EstadoExpediente = Literal["activo", "archivado"]


@dataclass
class Expediente:
    """Expediente procesal del asistente-legal.

    Atributos:
        id: Identificador interno. None si la entidad no fue persistida aun.
        numero_caso: Identificador procesal unico (ej.formula TSJM). UNIQUE.
        tipo_proceso: Tipo de ingreso. Ver TipoProceso.
        tribunal_origen: Tribunal del cual proviene el caso.
        procesado_nombre: Nombre del procesado.
        procesado_grado: Grado militar del procesado. None si no aplica.
        delito: Calificacion delictiva del caso.
        sentencia_origen: Texto/resumen de la sentencia de origen. None si
            el expediente se abre como consulta sin sentencia previa.
        fojas_total: Cantidad total de fojas del expediente. None si no
            se conoce al momento de apertura.
        estado: Estado del expediente. Por defecto 'activo'.
        abierto_por: ID del usuario que abrio el expediente (FK a usuario.id).
            El dominio guarda el int; el adapter resuelve la FK.
        created_at: Fecha/hora de apertura. None antes de persistir.
    """

    id: int | None
    numero_caso: str
    tipo_proceso: TipoProceso
    tribunal_origen: str
    procesado_nombre: str
    delito: str
    abierto_por: int
    procesado_grado: str | None = None
    sentencia_origen: str | None = None
    fojas_total: int | None = None
    estado: EstadoExpediente = "activo"
    created_at: datetime | None = None
