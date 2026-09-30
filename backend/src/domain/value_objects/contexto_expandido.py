"""Value object: ContextoExpandido — output del ExpansorContexto (Sprint 5).

Contexto recuperado enriquecido con padres jerarquicos (BFS ascendente via
padre_ref_id FK self-ref en PG) + breadcrumbs para trazabilidad.

Regla Trail of Bits Sec 6: breadcrumbs resueltos contra PostgreSQL
(campo padre_ref_id FK self-referencial) — NO se confia en padre_ref_key
precalculado de Qdrant sin validacion contra PG.

Regla Trail of Bits Sec 6 (BLOQUEANTE): el contexto expandido NUNCA
incluye fragmentos de obras privadas de otros usuarios. El
ExpansorJerarquico usa EvaluadorVisibilidad para podarlos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.domain.entities.fragmento import Fragmento
from src.domain.value_objects.trazabilidad_pipeline import TrazabilidadPipeline

TipoRespuesta = Literal[
    "consulta_simple",
    "auto_vista_consulta",
    "auto_vista_apelacion_incidental",
    "dictamen_radicatoria_consulta",
    "dictamen_radicatoria_apelacion",
]


@dataclass(frozen=True, slots=True)
class ContextoExpandido:
    """Contexto recuperado enriquecido con padres jerarquicos (Sprint 5).

    Producido por ExpansorContexto. Usado por LLMClient (Sprint 6) para
    inyectar contexto juridico completo al prompt.

    Atributos:
        fragmentos_con_padres: Fragmentos hijo + padres ascendidos (hijos
            primero, despues padres). Regla 6: ningun padre de obra privada
            ajena.
        scores: Scores de los fragmentos (hijos conservan su score del reranker,
            padres heredan el score maximo del hijo que los alcanzo).
        query_original: Texto de la consulta original.
        tipo_respuesta: Tipo clasificado de respuesta.
        expediente_id: ID del expediente (None si consulta_simple).
        breadcrumbs: Una tupla por fragmento hijo, path de padre_ref_key desde
            raiz hasta el hijo. Si un nodo no tiene padre_ref_key, se usa
            qdrant_point_id como fallback.
        trazabilidad: Metricas de latencia y conteo por fase. None si no se
            proceso todavia (backward compat).
    """

    fragmentos_con_padres: tuple[Fragmento, ...]
    scores: tuple[float, ...]
    query_original: str
    tipo_respuesta: TipoRespuesta
    expediente_id: int | None
    breadcrumbs: tuple[tuple[str, ...], ...] = ()
    trazabilidad: TrazabilidadPipeline | None = None
    latencia_ms: int | None = None
