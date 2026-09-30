"""Value object: ContextoRecuperado — output del PipelineRAG (Sprint 3).

Contiene los fragmentos rerankeados con sus scores, el tipo de respuesta
clasificado, y el ID del expediente si la consulta lo requiere.

Regla Clean Architecture: frozen dataclass (inmutable). El adapter lo
construye; la capa de aplicacion lo consume; el valor nunca se modifica
en transito.

Output contract hacia Sprint 5 (ExpansorContexto recibe ContextoRecuperado)
y Sprint 6 (LLMClient recibe ContextoExpandido).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TipoRespuesta = Literal[
    "consulta_simple",
    "auto_vista_consulta",
    "auto_vista_apelacion_incidental",
    "dictamen_radicatoria_consulta",
    "dictamen_radicatoria_apelacion",
    "dictamen_fondo",
    "relacion_obrados",
]


@dataclass(frozen=True, slots=True)
class ContextoRecuperado:
    """Output del pipeline RAG (fases 1-3). Inmutable.

    Atributos:
        fragmentos: Tupla de fragmentos rerankeados (ordenados por score desc).
        scores: Tupla de scores correspondientes (misma posicion que fragmentos).
        query_original: Texto de la consulta original del usuario.
        tipo_respuesta: Tipo clasificado de respuesta juridica.
        expediente_id: ID del expediente (None si consulta_simple).
        latencia_ms: Milisegundos totales del pipeline. None en Sprint 3.
    """

    fragmentos: tuple[Any, ...]
    scores: tuple[float, ...]
    query_original: str
    tipo_respuesta: TipoRespuesta
    expediente_id: int | None
    latencia_ms: int | None = None
