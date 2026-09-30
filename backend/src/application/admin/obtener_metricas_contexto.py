"""Use case: ObtenerMetricasContexto — HU-22 metricas de expansion (Sprint 5).

Lee consulta_historial, extrae la sub-clave `expansion` de
fuentes_recuperadas JSONB, agrega por rango temporal.

HU-22: endpoint API JSON, sin panel frontend. Consumible por curl/Postman.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports.consulta_historial_repo import (
        ConsultaHistorialRepo,
    )


@dataclass(frozen=True, slots=True)
class MetricaItem:
    """Una consulta individual con su trazabilidad de expansion."""

    consulta_id: int
    usuario_id: int
    latencia_expansion_ms: int
    nodos_ascendidos: int
    breadcrumbs_count: int
    expansion_realizada: bool


@dataclass(frozen=True, slots=True)
class MetricasContexto:
    """Agregacion de metricas de expansion de las ultimas N consultas.

    Atributos:
        total_consultas: Total de consultas con datos de expansion.
        expansion_realizada_count: Cuantas tuvieron expansion_realizada=True.
        latencia_expansion_promedio_ms: Promedio de latencia de expansion.
        nodos_ascendidos_promedio: Promedio de padres ascendidos.
        breadcrumbs_count_promedio: Promedio de breadcrumbs generados.
        iteraciones: Lista de MetricaItem por consulta individual.
    """

    total_consultas: int
    expansion_realizada_count: int
    latencia_expansion_promedio_ms: float
    nodos_ascendidos_promedio: float
    breadcrumbs_count_promedio: float
    iteraciones: tuple[MetricaItem, ...]


async def ejecutar(
    repo: ConsultaHistorialRepo,
    limite: int = 100,
) -> MetricasContexto:
    """Agrega trazabilidad de expansion de las ultimas N consultas.

    Args:
        repo: Repositorio del historial de consultas.
        limite: Maximo de consultas a analizar (default 100).

    Returns:
        MetricasContexto con promedios e iteraciones individuales.
    """
    items, _total = await repo.listar_todas(pagina=1, por_pagina=limite)

    metricas: list[MetricaItem] = []
    for h in items:
        fuentes = h.fuentes_recuperadas or {}
        expansion = fuentes.get("expansion", {})
        realizado = expansion.get("realizada", False)
        metricas.append(
            MetricaItem(
                consulta_id=h.id or 0,
                usuario_id=h.usuario_id or 0,
                latencia_expansion_ms=expansion.get("latencia_expansion_ms", 0),
                nodos_ascendidos=expansion.get("nodos_ascendidos", 0),
                breadcrumbs_count=expansion.get("breadcrumbs_count", 0),
                expansion_realizada=realizado,
            )
        )

    total = len(metricas)
    if total == 0:
        return MetricasContexto(
            total_consultas=0,
            expansion_realizada_count=0,
            latencia_expansion_promedio_ms=0.0,
            nodos_ascendidos_promedio=0.0,
            breadcrumbs_count_promedio=0.0,
            iteraciones=(),
        )

    realizadas = sum(1 for m in metricas if m.expansion_realizada)
    latencia_prom = sum(m.latencia_expansion_ms for m in metricas) / total
    nodos_prom = sum(m.nodos_ascendidos for m in metricas) / total
    breadcrumbs_prom = sum(m.breadcrumbs_count for m in metricas) / total

    return MetricasContexto(
        total_consultas=total,
        expansion_realizada_count=realizadas,
        latencia_expansion_promedio_ms=round(latencia_prom, 2),
        nodos_ascendidos_promedio=round(nodos_prom, 2),
        breadcrumbs_count_promedio=round(breadcrumbs_prom, 2),
        iteraciones=tuple(metricas),
    )
