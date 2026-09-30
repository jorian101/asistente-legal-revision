"""Router admin: metricas de contexto + observabilidad pipeline (Sprint 7).

Endpoints:
- GET /admin/metricas/contexto — API JSON (HU-22, Sprint 5)
- GET /admin/metricas/salud — estado PG/Qdrant + sesiones activas (HU-22)
- GET /admin/pipeline/events — SSE stream de eventos en vivo (Sprint 7)
Solo admin autenticado.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.adapters.http.dependencies import (
    AuditLogRepoDep,
    ConfiguracionRAGRepoDep,
    ConsultaHistorialRepoDep,
    SaludSistemaRepoDep,
    require_permiso,
)
from src.application.admin import obtener_metricas_contexto
from src.application.admin.audit import listar_auditoria
from src.application.admin.obtener_metricas_salud import ejecutar as ejecutar_salud
from src.application.observability import get_event_bus
from src.config import get_settings
from src.domain.entities.usuario import Usuario

router = APIRouter(prefix="/admin", tags=["admin"])


class AuditoriaItemDTO(BaseModel):
    accion: str
    entidad: str | None
    entidad_id: int | None
    usuario_id: int | None
    detalle: dict | None
    created_at: str | None


class PaginaAuditoriaDTO(BaseModel):
    items: list[AuditoriaItemDTO]
    total: int


class HistorialPipelineItemDTO(BaseModel):
    """Ejecución de pipeline persistida (replay para la Sala de Control)."""

    id: int
    usuario_id: int
    usuario_carnet: str
    usuario_nombre: str
    expediente_id: int | None
    pregunta: str
    respuesta: str | None
    tipo_respuesta: str | None
    latencia_ms: int | None
    modelo_llm: str | None
    fuentes_recuperadas: dict | None
    created_at: str | None
    estado: str | None = None


class PaginaHistorialPipelineDTO(BaseModel):
    items: list[HistorialPipelineItemDTO]
    total: int


class ResumenTipoDTO(BaseModel):
    tipo_respuesta: str
    cantidad: int


class ResumenModeloDTO(BaseModel):
    modelo_llm: str | None
    cantidad: int
    latencia_promedio_ms: float | None


class ResumenUsuarioDTO(BaseModel):
    usuario_id: int
    usuario_carnet: str
    usuario_nombre: str
    cantidad: int


class ResumenDiaDTO(BaseModel):
    fecha: str
    cantidad: int


class EndpointActivoDTO(BaseModel):
    """Endpoint que el pipeline usa de verdad, para mostrarlo en el Dashboard.

    Solo {id, provider, model}: ni base_url ni api_key_env salen del backend
    (Trail of Bits Regla 3).
    """

    id: str
    provider: str
    model: str


class DashboardResumenDTO(BaseModel):
    total_consultas: int
    en_progreso: int
    completadas: int
    con_error: int
    por_tipo: list[ResumenTipoDTO]
    por_modelo: list[ResumenModeloDTO]
    por_usuario: list[ResumenUsuarioDTO]
    consultas_por_dia: list[ResumenDiaDTO]
    llm_endpoint: EndpointActivoDTO | None
    embedding_endpoint: EndpointActivoDTO | None
    reranker_endpoint: EndpointActivoDTO | None


class MetricaItemDTO(BaseModel):
    consulta_id: int
    usuario_id: int
    latencia_expansion_ms: int
    nodos_ascendidos: int
    breadcrumbs_count: int
    expansion_realizada: bool


class MetricasContextoDTO(BaseModel):
    total_consultas: int
    expansion_realizada_count: int
    latencia_expansion_promedio_ms: float
    nodos_ascendidos_promedio: float
    breadcrumbs_count_promedio: float
    iteraciones: list[MetricaItemDTO]


class MetricasSaludDTO(BaseModel):
    postgres_ok: bool
    qdrant_ok: bool
    qdrant_puntos: int
    sesiones_activas: int


@router.get("/metricas/contexto", response_model=MetricasContextoDTO)
async def obtener_metricas_contexto_endpoint(
    _admin: Annotated[Usuario, Depends(require_permiso("metricas", "leer"))],
    historial_repo: ConsultaHistorialRepoDep,
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
) -> MetricasContextoDTO:
    """HU-22: metricas de expansion de contexto (solo admin)."""
    metricas = await obtener_metricas_contexto.ejecutar(
        repo=historial_repo,
        limite=limite,
    )
    return MetricasContextoDTO(
        total_consultas=metricas.total_consultas,
        expansion_realizada_count=metricas.expansion_realizada_count,
        latencia_expansion_promedio_ms=metricas.latencia_expansion_promedio_ms,
        nodos_ascendidos_promedio=metricas.nodos_ascendidos_promedio,
        breadcrumbs_count_promedio=metricas.breadcrumbs_count_promedio,
        iteraciones=[MetricaItemDTO(**asdict(item)) for item in metricas.iteraciones],
    )


@router.get("/metricas/salud", response_model=MetricasSaludDTO)
async def obtener_metricas_salud_endpoint(
    _admin: Annotated[Usuario, Depends(require_permiso("metricas", "leer"))],
    salud_repo: SaludSistemaRepoDep,
) -> MetricasSaludDTO:
    """HU-22: salud de infraestructura (solo admin).

    Pings PostgreSQL y Qdrant (con conteo de puntos del corpus) mas
    sesiones activas (suscriptores SSE del bus). Nunca lanza 500 por
    componente caido: lo reporta con ok=False.
    """
    metricas = await ejecutar_salud(salud_repo=salud_repo, bus=get_event_bus())
    return MetricasSaludDTO(
        postgres_ok=metricas.postgres_ok,
        qdrant_ok=metricas.qdrant_ok,
        qdrant_puntos=metricas.qdrant_puntos,
        sesiones_activas=metricas.sesiones_activas,
    )


@router.get("/auditoria", response_model=PaginaAuditoriaDTO)
async def get_auditoria(
    _admin: Annotated[Usuario, Depends(require_permiso("auditoria", "leer"))],
    audit_repo: AuditLogRepoDep,
    accion: Annotated[str | None, Query()] = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
) -> PaginaAuditoriaDTO:
    """Trail of Bits R6: consulta el log de auditoria (solo admin).

    Append-only: registra QUÉ hizo QUIÉN sobre QUÉ entidad y CUÁNDO.
    Filtro opcional por accion (login, crear_expediente, publicar_borrador...).
    """
    registros = await listar_auditoria(
        repo=audit_repo,
        accion=accion,
        limit=limite,
    )
    return PaginaAuditoriaDTO(
        items=[
            AuditoriaItemDTO(
                accion=reg.accion,
                entidad=reg.entidad,
                entidad_id=reg.entidad_id,
                usuario_id=reg.usuario_id,
                detalle=reg.detalle,
                created_at=reg.created_at.isoformat() if reg.created_at else None,
            )
            for reg in registros
        ],
        total=len(registros),
    )


@router.get("/pipeline/historial", response_model=PaginaHistorialPipelineDTO)
async def historial_pipeline(
    _admin: Annotated[Usuario, Depends(require_permiso("sala_control", "leer"))],
    historial_repo: ConsultaHistorialRepoDep,
    usuario_id: int | None = Query(None),
    expediente_id: int | None = Query(None),
    tipo_respuesta: str | None = Query(None),
    estado: str | None = Query(None),
    fecha_desde: Annotated[datetime | None, Query()] = None,
    fecha_hasta: Annotated[datetime | None, Query()] = None,
    texto: str | None = Query(None),
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginaHistorialPipelineDTO:
    """Historial persistido de ejecuciones del pipeline (replay para Sala).

    El bus de eventos es in-memory: solo entrega eventos posteriores a la
    conexión. Este endpoint permite a la Sala de Control reconstruir
    ejecuciones pasadas desde consulta_historial, con los mismos filtros que
    la auditoría admin (usuario, expediente, tipo, estado, rango de fechas y
    texto). El join a usuario da carnet/nombre reales.
    """
    items, total = await historial_repo.listar_admin(
        usuario_id=usuario_id,
        expediente_id=expediente_id,
        tipo_respuesta=tipo_respuesta,
        estado=estado,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        texto=texto,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    return PaginaHistorialPipelineDTO(
        items=[
            HistorialPipelineItemDTO(
                id=h.id,
                usuario_id=h.usuario_id,
                usuario_carnet=h.usuario_carnet,
                usuario_nombre=h.usuario_nombre,
                expediente_id=h.expediente_id,
                pregunta=h.pregunta,
                respuesta=h.respuesta,
                tipo_respuesta=h.tipo_respuesta,
                latencia_ms=h.latencia_ms,
                modelo_llm=h.modelo_llm,
                fuentes_recuperadas=h.fuentes_recuperadas,
                created_at=h.created_at.isoformat() if h.created_at else None,
                estado=h.estado,
            )
            for h in items
        ],
        total=total,
    )


def _endpoint_activo(endpoint: dict | None) -> EndpointActivoDTO | None:
    """Convierte un endpoint de settings al DTO del Dashboard, o None."""
    if endpoint is None:
        return None
    return EndpointActivoDTO(
        id=endpoint["id"],
        provider=endpoint["provider"],
        model=endpoint["model"],
    )


def _resolver_endpoint(
    resolver: Callable[[str | None], dict], endpoint_id: str | None
) -> dict | None:
    """Resuelve el endpoint activo, o None si no hay ninguno que usar.

    `resolver` es `Settings.llm_endpoint` / `.embedding_endpoint` /
    `.reranker_endpoint`. Levanta RuntimeError cuando el .env no define
    ninguno (el reranker deshabilitado es un estado válido) y KeyError
    cuando el id guardado en la singleton ya no existe en el .env: en los
    dos casos el Dashboard muestra "no configurado" en vez de inventar un
    modelo.
    """
    try:
        return resolver(endpoint_id)
    except (RuntimeError, KeyError):
        return None


@router.get("/dashboard/resumen", response_model=DashboardResumenDTO)
async def dashboard_resumen(
    _admin: Annotated[Usuario, Depends(require_permiso("metricas", "leer"))],
    historial_repo: ConsultaHistorialRepoDep,
    config_repo: ConfiguracionRAGRepoDep,
) -> DashboardResumenDTO:
    """Dashboard admin: resumen general de chats y de los modelos activos.

    Agrega consulta_historial (totales, estado, tipo, modelo con latencia
    media, usuario y por dia) y suma los endpoints activos de
    configuracion_rag (LLM, embeddings y reranker).
    """
    resumen = await historial_repo.resumen_dashboard()
    cfg = await config_repo.get_config()
    settings = get_settings()
    return DashboardResumenDTO(
        total_consultas=resumen.total_consultas,
        en_progreso=resumen.en_progreso,
        completadas=resumen.completadas,
        con_error=resumen.con_error,
        por_tipo=[ResumenTipoDTO(**asdict(t)) for t in resumen.por_tipo],
        por_modelo=[ResumenModeloDTO(**asdict(m)) for m in resumen.por_modelo],
        por_usuario=[ResumenUsuarioDTO(**asdict(u)) for u in resumen.por_usuario],
        consultas_por_dia=[ResumenDiaDTO(**asdict(d)) for d in resumen.consultas_por_dia],
        llm_endpoint=_endpoint_activo(
            _resolver_endpoint(settings.llm_endpoint, cfg.llm_endpoint_id)
        ),
        # Los embeddings no tienen selector en la singleton: el runtime usa
        # siempre el primer endpoint (build_embedder(None), dependencies.py).
        embedding_endpoint=_endpoint_activo(_resolver_endpoint(settings.embedding_endpoint, None)),
        reranker_endpoint=_endpoint_activo(
            _resolver_endpoint(settings.reranker_endpoint, cfg.reranker_endpoint_id)
        ),
    )


@router.get("/pipeline/events")
async def pipeline_events_sse(
    _admin: Annotated[Usuario, Depends(require_permiso("sala_control", "leer"))],
    request: Request,
    filtro_usuario: Annotated[int | None, Query(description="Filtrar por usuario_id")] = None,
    filtro_expediente: Annotated[int | None, Query(description="Filtrar por expediente_id")] = None,
) -> StreamingResponse:
    """SSE stream de eventos del pipeline RAG en vivo (solo admin).

    Filtros opcionales:
    - filtro_usuario: solo eventos de ese usuario_id
    - filtro_expediente: solo eventos de ese expediente_id

    Eventos: fase_iniciada, fase_completada, pipeline_completado, pipeline_error
    Formato: data: {json}\n\n (SSE estándar)
    """
    bus = get_event_bus()

    async def event_generator():
        """Yield eventos SSE hasta que el cliente se desconecte."""
        async for evento in bus.subscribe():
            # Filtrar si se especificaron filtros
            if filtro_usuario is not None and evento.usuario_id != filtro_usuario:
                continue
            if filtro_expediente is not None and evento.expediente_id != filtro_expediente:
                continue

            # Convertir dataclass a dict para JSON
            data = {
                "tipo": type(evento).__name__,
                "consulta_id": evento.consulta_id,
                "fase": getattr(evento, "fase", None),
                "timestamp_ms": evento.timestamp_ms,
                "usuario_id": evento.usuario_id,
                "usuario_nombre": evento.usuario_nombre,
                "expediente_id": evento.expediente_id,
                "tipo_respuesta": evento.tipo_respuesta,
            }

            # Añadir campos específicos por tipo de evento
            if hasattr(evento, "duracion_ms"):
                data["duracion_ms"] = evento.duracion_ms
                data["resumen_legible"] = evento.resumen_legible
                data["metadata"] = evento.metadata
            if hasattr(evento, "latencia_total_ms"):
                data["latencia_total_ms"] = evento.latencia_total_ms
                data["resumen_legible"] = evento.resumen_legible
                data["fragmentos_count"] = evento.fragmentos_count
            if hasattr(evento, "fase_fallida"):
                data["fase_fallida"] = evento.fase_fallida
                data["mensaje_error"] = evento.mensaje_error
            if type(evento).__name__ == "GeneracionCompletada":
                data["resumen_legible"] = evento.resumen_legible
                data["respuesta"] = evento.respuesta
                data["tokens"] = evento.tokens

            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            # Check if client disconnected
            if await request.is_disconnected():
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
