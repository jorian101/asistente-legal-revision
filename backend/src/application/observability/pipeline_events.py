"""Eventos de observabilidad del pipeline RAG (Sprint 7).

Eventos inmutables que viajan por el bus. El bus no los interpreta;
solo los reenvía a los subscriptores. Cada evento lleva metadata
mínima para filtrado en el cliente (usuario_id, expediente_id, tipo_respuesta).

Nombres de fases en español (para UI no técnica):
- "entendiendo"      -> ClasificarTipoRespuesta
- "buscando"         -> HybridSearcher
- "reordenando"      -> RerankerService
- "expandiendo"      -> ExpansorContexto
- "generando"        -> LLM (Sprint 6)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

FasePipeline = Literal[
    "entendiendo",
    "buscando",
    "reordenando",
    "expandiendo",
    "generando",
]


@dataclass(frozen=True, slots=True)
class EventoPipeline:
    """Evento base del pipeline RAG."""

    consulta_id: int
    fase: FasePipeline
    timestamp_ms: int
    usuario_id: int
    usuario_nombre: str
    expediente_id: int | None
    tipo_respuesta: str | None


@dataclass(frozen=True, slots=True)
class FaseIniciada(EventoPipeline):
    """El pipeline entró en una fase."""

    pass


@dataclass(frozen=True, slots=True)
class FaseCompletada(EventoPipeline):
    """Una fase terminó con éxito."""

    duracion_ms: int
    resumen_legible: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PipelineCompletado(EventoPipeline):
    """Pipeline terminó con éxito (incluye fase generando si LLM configurado)."""

    latencia_total_ms: int
    resumen_legible: str
    fragmentos_count: int


@dataclass(frozen=True, slots=True)
class GeneracionCompletada(EventoPipeline):
    """La generacion del LLM termino y la respuesta se persistio.

    Se emite al cerrar el stream en GenerarBorrador (tras actualizar la
    respuesta en consulta_historial). La Sala de Control marca la fase
    'generando' como completada SOLO con este evento — PipelineCompletado
    se emite al terminar la RECUPERACION (fases 1-4), no la generacion.
    """

    resumen_legible: str
    respuesta: str = ""
    tokens: int | None = None


@dataclass(frozen=True, slots=True)
class PipelineError(EventoPipeline):
    """Error en alguna fase del pipeline."""

    fase_fallida: FasePipeline
    mensaje_error: str


@dataclass(frozen=True, slots=True)
class LLMTokensConsumidos:
    """Tokens consumidos por una llamada al LLM (emitido al cierre del stream).

    Independiente de FasePipeline — se emite una vez por request al LLM,
    al detectar el chunk de usage en la respuesta streaming.
    """

    consulta_id: int
    usuario_id: int
    modelo: str
    tokens_input: int
    tokens_output: int
    timestamp_ms: int


# Union para tipado exhaustivo en handlers
EventoPipelineUnion = (
    FaseIniciada
    | FaseCompletada
    | PipelineCompletado
    | GeneracionCompletada
    | PipelineError
    | LLMTokensConsumidos
)


def fase_a_legible(fase: FasePipeline) -> str:
    """Mapa interno -> legible para UI no técnica."""
    return {
        "entendiendo": "Entendiendo tu pregunta",
        "buscando": "Buscando en el corpus jurídico",
        "reordenando": "Reordenando por relevancia",
        "expandiendo": "Agregando contexto",
        "generando": "Generando respuesta",
    }.get(fase, fase)


def resumen_legible_fase(
    fase: FasePipeline,
    metadata: dict[str, Any],
) -> str:
    """Genera texto legible para el jurado (no técnico)."""
    if fase == "entendiendo":
        return f"Clasificamos la consulta como '{metadata.get('tipo_respuesta', 'desconocido')}'"
    if fase == "buscando":
        normas = metadata.get("normas_consultadas", [])
        return (
            f"Buscamos en {metadata.get('fragmentos_encontrados', 0)} fragmentos "
            f"de {len(normas)} normas" + (f" ({', '.join(normas)})" if normas else "")
        )
    if fase == "reordenando":
        modelo = metadata.get("modelo", "reranker")
        fallback = " (usó fallback)" if metadata.get("fallback") else ""
        return (
            f"Reordenamos por relevancia con {modelo}{fallback} — "
            f"top {metadata.get('top_k_final', '?')} seleccionados"
        )
    if fase == "expandiendo":
        return (
            f"Expandimos con {metadata.get('nodos_ascendidos', 0)} nodos padre "
            f"(breadcrumbs: {metadata.get('breadcrumbs_count', 0)})"
        )
    if fase == "generando":
        tokens = metadata.get("tokens", "?")
        return f"Generamos respuesta ({tokens} tokens)"
    return "Fase completada"
