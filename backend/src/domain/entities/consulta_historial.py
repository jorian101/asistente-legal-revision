"""Entidad de dominio ConsultaHistorial — registro de una consulta al asistente.

Regla Clean Architecture: dataclass pura, sin SQLAlchemy ni Pydantic.
El ORM vive en adapters/postgres/models/consulta_historial.py.

Una fila por consulta realizada por un usuario (D9 — base para KPIs
EASI-RAG y Analisis de Errores de tesis). En Sprint 3 la respuesta es NULL
(la genera el LLM en Sprint 6); en su lugar se persiste el
ContextoRecuperado serializado en `fuentes_recuperadas` (JSONB).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ConsultaHistorial:
    """Registro de una consulta al asistente RAG.

    Atributos:
        id: PK interno. None antes de persistir.
        expediente_id: FK a expediente (None si consulta_simple, D11).
        usuario_id: FK a usuario que realizo la consulta.
        pregunta: Texto de la consulta original.
        respuesta: Texto de la respuesta del LLM. None en Sprint 3 (D11).
        tipo_respuesta: Clasificacion de la consulta (D11).
        fuentes_recuperadas: ContextoRecuperado serializado (JSONB).
        latencia_ms: Latencia total del pipeline en ms.
        modelo_llm: Modelo LLM usado (None en Sprint 3).
        estado: Estado explicito del ciclo de vida: 'en_progreso' (insert),
            'completado' (respuesta persistida) o 'error' (pipeline fallo).
            La Sala de Control usa este campo en vez de inferir de NULLs.
        activo: Soft delete (False = entrada eliminada por su propietario).
            Default True.
        created_at: Timestamp de la consulta. None antes de persistir.
    """

    id: int | None
    expediente_id: int | None
    usuario_id: int
    pregunta: str
    respuesta: str | None
    tipo_respuesta: str | None
    fuentes_recuperadas: dict[str, Any] | None
    latencia_ms: int | None
    modelo_llm: str | None
    estado: str | None = None
    activo: bool = True
    created_at: datetime | None = None
