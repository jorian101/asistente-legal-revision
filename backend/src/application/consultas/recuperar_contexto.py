"""Use case: RecuperarContexto — ejecuta el pipeline RAG y persiste historial.

Sprint 3 entrega el primer caso de uso de consulta: dado una consulta +
usuario_id (+ expediente_id opcional), orquesta el pipeline RAG
(clasificar -> buscar -> reranker) y persiste el resultado en
`consulta_historial` para KPIs EASI-RAG y Analisis de Errores (D9).

Sprint 5 extiende con `expandir: bool=True`: si el pipeline tiene
expansor configurado, la Fase 4 produce ContextoExpandido con
breadcrumbs y trazabilidad — serializado en el JSONB `expansion`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.entities.consulta_historial import ConsultaHistorial
from src.domain.value_objects.contexto_recuperado import ContextoRecuperado

if TYPE_CHECKING:
    from src.application.ports.consulta_historial_repo import (
        ConsultaHistorialRepo,
    )
    from src.application.services.pipeline_rag import PipelineRAG


@dataclass(frozen=True, slots=True)
class ConsultaRequest:
    """Input del use case RecuperarContexto (T2: tipo_forzado para fondo/relación)."""

    consulta: str
    usuario_id: int
    expediente_id: int | None = None
    obra_ids: list[int] | None = None
    expandir: bool = True
    tipo_forzado: str | None = None
    corpus_refs: list[str] | None = None


@dataclass(frozen=True, slots=True)
class ResultadoConsulta:
    """Output del use case: contexto recuperado + id del historial."""

    contexto: ContextoRecuperado
    historial_id: int


async def ejecutar(
    req: ConsultaRequest,
    pipeline: PipelineRAG,
    historial_repo: ConsultaHistorialRepo,
) -> ResultadoConsulta:
    """Ejecuta el pipeline RAG y persiste el historial de la consulta.

    Args:
        req: ConsultaRequest con consulta, usuario_id, opcional expediente_id
            y expandir (default True).
        pipeline: PipelineRAG orquestador.
        historial_repo: Repositorio del historial de consultas.

    Returns:
        ResultadoConsulta con el ContextoRecuperado/ContextoExpandido y
        el id del historial.

    Raises:
        src.domain.exceptions.ConsultaSinExpedienteError: Si la consulta
            se clasifica como auto_vista_* y no se provee expediente_id.
    """
    contexto = await pipeline.ejecutar(
        consulta=req.consulta,
        usuario_id=req.usuario_id,
        expediente_id=req.expediente_id,
        obra_ids=req.obra_ids,
        tipo_forzado=req.tipo_forzado,
        corpus_refs=req.corpus_refs,
        expandir=req.expandir,
    )

    historial = ConsultaHistorial(
        id=None,
        expediente_id=contexto.expediente_id,
        usuario_id=req.usuario_id,
        pregunta=req.consulta,
        respuesta=None,  # D11: NULL en Sprint 3 (LLM llega Sprint 6)
        tipo_respuesta=contexto.tipo_respuesta,
        fuentes_recuperadas=_serializar_contexto(contexto),
        latencia_ms=contexto.latencia_ms,
        modelo_llm=None,
    )

    historial_persistido = await historial_repo.guardar(historial)

    return ResultadoConsulta(
        contexto=contexto,
        historial_id=historial_persistido.id,
    )


def _serializar_contexto(contexto: ContextoRecuperado) -> dict:
    """Serializa ContextoRecuperado/ContextoExpandido a dict para JSONB.

    Sprint 5: si el contexto es ContextoExpandido, agrega la sub-clave
    `expansion` con latencias, conteos y breadcrumbs_count.
    """
    from src.domain.value_objects.contexto_expandido import ContextoExpandido

    is_expandido = isinstance(contexto, ContextoExpandido)
    fragmentos = contexto.fragmentos_con_padres if is_expandido else contexto.fragmentos
    scores = contexto.scores
    latencia_ms = contexto.latencia_ms

    base: dict = {
        "tipo_respuesta": contexto.tipo_respuesta,
        "expediente_id": contexto.expediente_id,
        "fragmentos_count": len(fragmentos),
        "scores": list(scores),
        "latencia_ms": latencia_ms,
        "fragmentos": [
            {
                "id": frag.id,
                "norma_id": frag.norma_id,
                "obra_id": frag.obra_id,
                "expediente_id": frag.expediente_id,
                "qdrant_point_id": frag.qdrant_point_id,
                "texto": frag.texto,
                "padre_ref_key": frag.padre_ref_key,
                "nivel_jerarquico": frag.nivel_jerarquico,
            }
            for frag in fragmentos
        ],
    }

    if is_expandido:
        traz = contexto.trazabilidad
        base["expansion"] = {
            "realizada": True,
            "latencia_expansion_ms": traz.latencia_expansion_ms if traz else 0,
            "nodos_ascendidos": traz.nodos_ascendidos if traz else 0,
            "breadcrumbs_count": traz.breadcrumbs_count if traz else 0,
            "fragmentos_originales_count": (traz.fragmentos_originales_count if traz else 0),
            "fragmentos_expandidos_count": (traz.fragmentos_expandidos_count if traz else 0),
        }

    return base
