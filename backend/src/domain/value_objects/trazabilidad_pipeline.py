"""Value object: TrazabilidadPipeline — metricas de observabilidad (Sprint 5).

Registra las latencias y contadores de cada fase del pipeline RAG para que
el endpoint HU-22 (GET /admin/metricas/contexto) pueda agregarlos.

Invariante: latencia_expansion_ms == 0 si y solo si expansion_realizada == False.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TrazabilidadPipeline:
    """Metricas de trazabilidad del pipeline RAG (fases 1-4).

    Atributos:
        latencia_busqueda_ms: Milisegundos de la fase 2 (busqueda hibrida).
        latencia_reranking_ms: Milisegundos de la fase 3 (reranker).
        latencia_expansion_ms: Milisegundos de la fase 4 (expansion jerarquica).
            0 si no se ejecuto la expansion.
        nodos_ascendidos: Cuantos padres jerarquicos se agregaron al contexto.
        fragmentos_originales_count: Fragmentos del ContextoRecuperado (pre-expansion).
        fragmentos_expandidos_count: Fragmentos totales post-expansion (hijos + padres).
        breadcrumbs_count: Total de nodos en todos los breadcrumbs.
        expansion_realizada: True si la Fase 4 se ejecuto.
    """

    latencia_busqueda_ms: int
    latencia_reranking_ms: int
    latencia_expansion_ms: int
    nodos_ascendidos: int
    fragmentos_originales_count: int
    fragmentos_expandidos_count: int
    breadcrumbs_count: int
    expansion_realizada: bool
