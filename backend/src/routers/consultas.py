"""Router de consultas RAG (Sprint 3 — Motor de Recuperacion + Sprint 6 LLM).

Endpoints:
  POST /consultas/               — ejecutar consulta, devolver ContextoRecuperado
  POST /consultas/responder      — ejecutar consulta + LLM streaming (Sprint 6)
  GET  /consultas/historial      — historial paginado del usuario

Seguridad (Regla 4 + D4):
- require_consulta_user bloquea administrador.
- usuario_id del JWT (no del request) para garantizar privacidad.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.adapters.http.dependencies import (
    ConsultaHistorialRepoDep,
    ExpedienteRepoDep,
    NormaRepoDep,
    ObraRepoDep,
    PipelineRAGDep,
    require_permiso,
)
from src.adapters.http.dependencies_borradores import (
    GenerarBorradorDep,
)
from src.application.borradores.generar_borrador import (
    GenerarBorradorInput,
)
from src.application.consultas.eliminar_entrada_historial import (
    eliminar_entrada_historial,
)
from src.application.consultas.obtener_fuentes_historial import (
    FuentesConsulta,
)
from src.application.consultas.obtener_fuentes_historial import (
    ejecutar as ejecutar_obtener_fuentes,
)
from src.application.consultas.recuperar_contexto import (
    ConsultaRequest,
)
from src.application.consultas.recuperar_contexto import (
    ejecutar as ejecutar_recuperar,
)
from src.application.consultas.sugerir_argumentacion import ejecutar_sugerencia
from src.domain.entities.usuario import Usuario
from src.domain.exceptions import (
    ConsultaSinExpedienteError,
    FaltaCompetenciaError,
    RequisitosIncompletosError,
    VarianteApelacionNoSoportadaError,
)
from src.domain.value_objects.contexto_expandido import ContextoExpandido
from src.domain.value_objects.contexto_recuperado import (
    ContextoRecuperado,
    TipoRespuesta,
)

router = APIRouter(prefix="/consultas", tags=["consultas"])


# ----- DTOs ---------------------------------------------------------


class ConsultaBody(BaseModel):
    """Body del POST /consultas/."""

    consulta: str = Field(min_length=3, description="Texto de la consulta")
    expediente_id: int | None = Field(
        default=None,
        description="FK del expediente (obligatorio para auto_vista_*)",
    )
    obra_ids: list[int] | None = Field(
        default=None,
        description="Obras del expediente a consultar (todas si None). Regla 5.",
    )
    chat_id: int | None = Field(
        default=None,
        description="Chat activo: habilita memoria conversacional del turno",
    )
    tipo_forzado: str | None = Field(
        default=None,
        description="TipoRespuesta forzado desde Acción rápida (T2)",
    )
    corpus_refs: list[str] | None = Field(
        default=None,
        description="Abreviaturas N2/N3 ad-hoc sin crear puntero (T1)",
    )


class FragmentoResultadoDTO(BaseModel):
    """Fragmento recuperado (Sprint 3 — sin respuesta LLM)."""

    id: int | None
    norma_id: int | None
    obra_id: int | None
    expediente_id: int | None
    qdrant_point_id: str
    texto: str
    padre_ref_key: str | None
    nivel_jerarquico: int | None


class ContextoRecuperadoDTO(BaseModel):
    """Output del POST /consultas/ en Sprint 3.

    La respuesta del LLM llega en Sprint 6 (D11). Mientras tanto el
    frontend muestra el ContextoRecuperado directamente.
    """

    tipo_respuesta: TipoRespuesta
    expediente_id: int | None
    fragmentos: list[FragmentoResultadoDTO]
    scores: list[float]
    latencia_ms: int | None
    historial_id: int


class HistorialItemDTO(BaseModel):
    """Item del historial de consultas."""

    id: int
    expediente_id: int | None
    pregunta: str
    respuesta: str | None
    tipo_respuesta: str | None
    latencia_ms: int | None
    modelo_llm: str | None
    created_at: str | None


class HistorialDetalleDTO(BaseModel):
    """Detalle de una consulta para reanudación tras recarga."""

    id: int
    pregunta: str
    respuesta: str | None
    estado: str | None = None
    tipo_respuesta: str | None = None
    modelo_llm: str | None = None


class PaginaHistorialDTO(BaseModel):
    """Pagina de historial."""

    items: list[HistorialItemDTO]
    total: int
    pagina: int
    por_pagina: int


class BloqueArgumentacionDTO(BaseModel):
    """Bloque de argumentación (G4 — output de SugerirArgumentacion)."""

    titulo: str
    tipo: str
    contenido: str
    fojas_referidas: list[str]
    normas_citadas: list[str]
    prioridad: str


class SugerenciaArgumentacionDTO(BaseModel):
    """Sugerencia de argumentación (G4 — endpoint Fase 5b)."""

    tipo_respuesta: str
    fundamentos_hecho: list[BloqueArgumentacionDTO]
    fundamentos_derecho: list[BloqueArgumentacionDTO]
    vicios_sanear: list[BloqueArgumentacionDTO]
    alertas_competencia: list[BloqueArgumentacionDTO]
    alertas_plazos: list[BloqueArgumentacionDTO]
    resumen_ejecutivo: str
    total_bloques: int


# ----- Endpoints ----------------------------------------------------


@router.post(
    "/",
    response_model=ContextoRecuperadoDTO,
    status_code=status.HTTP_200_OK,
    summary="Ejecutar consulta RAG (Sprint 3 sin LLM)",
)
async def post_consulta(
    body: ConsultaBody,
    current_user: Annotated[Usuario, Depends(require_permiso("consultar", "crear"))],
    pipeline: PipelineRAGDep,
    historial_repo: ConsultaHistorialRepoDep,
) -> ContextoRecuperadoDTO:
    """Recibe una consulta, ejecuta el pipeline RAG (fases 1-3) y persiste el resultado.

    En Sprint 3 la respuesta es NULL (D11); el output son los fragmentos
    rerankeados con scores. El LLM se inyecta en Sprint 6.
    """
    try:
        resultado = await ejecutar_recuperar(
            ConsultaRequest(
                consulta=body.consulta,
                usuario_id=current_user.id,
                expediente_id=body.expediente_id,
                obra_ids=body.obra_ids,
                tipo_forzado=body.tipo_forzado,
                corpus_refs=body.corpus_refs,
            ),
            pipeline,
            historial_repo,
        )
    except (
        ConsultaSinExpedienteError,
        VarianteApelacionNoSoportadaError,
    ) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        ) from e

    contexto: ContextoRecuperado = resultado.contexto
    # Sprint 5: el pipeline puede devolver ContextoExpandido (fragmentos_con_padres)
    # o ContextoRecuperado (fragmentos). Mapear ambos al DTO.
    if isinstance(contexto, ContextoExpandido):
        fragmentos = contexto.fragmentos_con_padres
        scores = contexto.scores
    else:
        fragmentos = contexto.fragmentos
        scores = contexto.scores
    return ContextoRecuperadoDTO(
        tipo_respuesta=contexto.tipo_respuesta,
        expediente_id=contexto.expediente_id,
        fragmentos=[
            FragmentoResultadoDTO(
                id=frag.id,
                norma_id=frag.norma_id,
                obra_id=frag.obra_id,
                expediente_id=frag.expediente_id,
                qdrant_point_id=frag.qdrant_point_id,
                texto=frag.texto,
                padre_ref_key=frag.padre_ref_key,
                nivel_jerarquico=frag.nivel_jerarquico,
            )
            for frag in fragmentos
        ],
        scores=list(scores),
        latencia_ms=contexto.latencia_ms,
        historial_id=resultado.historial_id,
    )


@router.post(
    "/sugerir-argumentacion",
    response_model=SugerenciaArgumentacionDTO,
    status_code=status.HTTP_200_OK,
    summary="Sugerir argumentación jurídica desde el contexto RAG (G4)",
)
async def post_sugerir_argumentacion(
    body: ConsultaBody,
    current_user: Annotated[Usuario, Depends(require_permiso("consultar", "crear"))],
    pipeline: PipelineRAGDep,
    expediente_repo: ExpedienteRepoDep,
    obra_repo: ObraRepoDep,
) -> SugerenciaArgumentacionDTO:
    """Ejecuta el pipeline RAG y devuelve sugerencia estructurada de argumentación.

    Corre ExtraerHechosYConcordancias (G3) + SugerirArgumentacion (G4) sobre
    el contexto recuperado. Usado por el frontend para mostrar fundamentos
    de hecho/derecho, vicios a sanar y alertas de competencia/plazos.
    """
    try:
        contexto = await pipeline.ejecutar(
            consulta=body.consulta,
            usuario_id=current_user.id,
            expediente_id=body.expediente_id,
            obra_ids=body.obra_ids,
            expandir=True,
        )
        sug = await ejecutar_sugerencia(
            contexto,
            usuario_id=current_user.id,
            expediente_repo=expediente_repo,
            obra_repo=obra_repo,
        )
    except (
        ConsultaSinExpedienteError,
        VarianteApelacionNoSoportadaError,
    ) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        ) from e

    return SugerenciaArgumentacionDTO(
        tipo_respuesta=sug.tipo_respuesta,
        fundamentos_hecho=[_bloque_dto(b) for b in sug.fundamentos_hecho],
        fundamentos_derecho=[_bloque_dto(b) for b in sug.fundamentos_derecho],
        vicios_sanear=[_bloque_dto(b) for b in sug.vicios_sanear],
        alertas_competencia=[_bloque_dto(b) for b in sug.alertas_competencia],
        alertas_plazos=[_bloque_dto(b) for b in sug.alertas_plazos],
        resumen_ejecutivo=sug.resumen_ejecutivo,
        total_bloques=sug.total_bloques,
    )


def _bloque_dto(bloque) -> BloqueArgumentacionDTO:
    """Mapea BloqueArgumentacion (dominio) a DTO."""
    return BloqueArgumentacionDTO(
        titulo=bloque.titulo,
        tipo=bloque.tipo,
        contenido=bloque.contenido,
        fojas_referidas=list(bloque.fojas_referidas),
        normas_citadas=list(bloque.normas_citadas),
        prioridad=bloque.prioridad,
    )


@router.post(
    "/responder",
    status_code=status.HTTP_201_CREATED,
    summary="Ejecutar consulta RAG + generar respuesta LLM (streaming)",
)
async def post_consulta_responder(
    body: ConsultaBody,
    current_user: Annotated[Usuario, Depends(require_permiso("consultar", "crear"))],
    generar_borrador: GenerarBorradorDep,
) -> StreamingResponse:
    """Recibe una consulta, ejecuta pipeline RAG completo y stream LLM.

    Para consulta_simple: stream respuesta sin persistir borrador.
    Para auto_vista_* / dictamen_*: stream respuesta y persiste borrador.

    Headers de respuesta:
    - X-Borrador-Id: ID del borrador creado (vacío para consulta_simple)
    - X-Borrador-Tipo: tipo de respuesta clasificada
    """
    try:
        result = await generar_borrador.ejecutar(
            GenerarBorradorInput(
                consulta=body.consulta,
                usuario_id=current_user.id,
                expediente_id=body.expediente_id,
                obra_ids=body.obra_ids,
                chat_id=body.chat_id,
                tipo_forzado=body.tipo_forzado,
            )
        )
    except RequisitosIncompletosError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": str(e),
                "faltantes": sorted(e.faltantes),
                "tipo_proceso": e.tipo_proceso,
            },
        ) from e
    except ConsultaSinExpedienteError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        ) from e
    except FaltaCompetenciaError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        ) from e
    except VarianteApelacionNoSoportadaError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        ) from e
    except ValueError as e:
        if "no encontrado" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            ) from e
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        ) from e

    headers = {
        "X-Borrador-Tipo": result.tipo_respuesta,
        "X-Historial-Id": str(result.historial_id),
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        result.stream,
        media_type="text/plain; charset=utf-8",
        status_code=status.HTTP_201_CREATED,
        headers=headers,
    )


@router.get(
    "/historial",
    response_model=PaginaHistorialDTO,
    status_code=status.HTTP_200_OK,
    summary="Historial del usuario autenticado",
)
async def get_historial(
    current_user: Annotated[Usuario, Depends(require_permiso("conversaciones", "leer"))],
    historial_repo: ConsultaHistorialRepoDep,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(10, ge=1, le=100),
    expediente_id: int | None = Query(None),
) -> PaginaHistorialDTO:
    """Lista el historial del usuario autenticado (Regla 4: solo el suyo)."""
    items, total = await historial_repo.listar_por_usuario(
        usuario_id=current_user.id,
        expediente_id=expediente_id,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    items_dto: list[HistorialItemDTO] = []
    for h in items:
        if h.id is None:
            # Fila sin id no es esperable: guardar() siempre setea id.
            # Si ocurre es bug upstream. Fail-fast evita emitir id=0 que
            # rompe rowKey de React y confunde KPIs.
            raise RuntimeError(f"consulta_historial.id is None for pregunta={h.pregunta!r}")
        items_dto.append(
            HistorialItemDTO(
                id=h.id,
                expediente_id=h.expediente_id,
                pregunta=h.pregunta,
                respuesta=h.respuesta,
                tipo_respuesta=h.tipo_respuesta,
                latencia_ms=h.latencia_ms,
                modelo_llm=h.modelo_llm,
                created_at=h.created_at.isoformat() if h.created_at else None,
            )
        )
    return PaginaHistorialDTO(
        items=items_dto,
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
    )


@router.get(
    "/historial/{historial_id}",
    response_model=HistorialDetalleDTO,
    summary="Detalle de una consulta (reanudación tras recarga)",
)
async def get_historial_detalle(
    historial_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("conversaciones", "leer"))],
    historial_repo: ConsultaHistorialRepoDep,
) -> HistorialDetalleDTO:
    """Devuelve pregunta/respuesta/estado de UNA consulta propia (Regla 4).

    El frontend lo polea para reanudar streams interrumpidos por recarga:
    respuesta non-null = terminada (lista para mostrar).
    """
    h = await historial_repo.obtener_por_id(historial_id, current_user.id)
    if h is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrada de historial no encontrada.",
        )
    return HistorialDetalleDTO(
        id=h.id or 0,
        pregunta=h.pregunta,
        respuesta=h.respuesta,
        estado=h.estado,
        tipo_respuesta=h.tipo_respuesta,
        modelo_llm=h.modelo_llm,
    )


@router.delete(
    "/historial/{historial_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar entrada del historial (soft delete, Regla 4)",
)
async def delete_historial(
    historial_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("conversaciones", "eliminar"))],
    historial_repo: ConsultaHistorialRepoDep,
) -> None:
    """Soft delete de una entrada del historial del usuario (CRITICAL #4).

    Setea activo=False SOLO si la entrada pertenece al usuario (Regla 4).
    Conserva la fila para auditoria/KPIs (no borrado fisico).

    Raises:
        404: entrada inexistente o de otro usuario (no se revela cual).
    """
    eliminado = await eliminar_entrada_historial(
        historial_repo,
        historial_id=historial_id,
        usuario_id=current_user.id,
    )
    if not eliminado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrada de historial no encontrada.",
        )


# ----- Citas RAG por consulta (HU-18 UI) -----------------------------


class FragmentoCitaDTO(BaseModel):
    """Fragmento citable sanitizado (sin refs tecnicas ni UUIDs)."""

    id: int | None
    norma_id: int | None
    obra_id: int | None
    texto: str
    referencia: str | None
    nivel_jerarquico: int | None
    norma_nombre: str | None = None
    norma_abreviatura: str | None = None
    obra_tipo: str | None = None
    obra_fecha_documento: str | None = None
    expediente_numero: str | None = None
    categoria: str | None = None


class FuentesConsultaDTO(BaseModel):
    fragmentos: list[FragmentoCitaDTO]
    scores: list[float]


@router.get(
    "/historial/{historial_id}/fuentes",
    response_model=FuentesConsultaDTO,
    summary="Fuentes RAG de una consulta (citas del mensaje del asistente)",
)
async def get_fuentes_consulta(
    historial_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("conversaciones", "leer"))],
    historial_repo: ConsultaHistorialRepoDep,
    norma_repo: NormaRepoDep,
    obra_repo: ObraRepoDep,
    expediente_repo: ExpedienteRepoDep,
) -> FuentesConsultaDTO:
    """Fragmentos + scores persistidos para una consulta del usuario.

    Regla 4: solo la entrada propia; 404 encubierto si no existe o es de
    otro usuario. El frontend las muestra como citas bajo el mensaje bot.
    Enriquece en lectura: las citas dicen que son (norma/documento/expediente).
    """
    fuentes: FuentesConsulta | None = await ejecutar_obtener_fuentes(
        historial_repo,
        norma_repo,
        obra_repo,
        expediente_repo,
        historial_id=historial_id,
        usuario_id=current_user.id,
    )
    if fuentes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fuentes no disponibles.",
        )
    return FuentesConsultaDTO(
        fragmentos=[
            FragmentoCitaDTO(
                id=f.id,
                norma_id=f.norma_id,
                obra_id=f.obra_id,
                texto=f.texto,
                referencia=f.referencia,
                nivel_jerarquico=f.nivel_jerarquico,
                norma_nombre=f.norma_nombre,
                norma_abreviatura=f.norma_abreviatura,
                obra_tipo=f.obra_tipo,
                obra_fecha_documento=f.obra_fecha_documento,
                expediente_numero=f.expediente_numero,
                categoria=f.categoria,
            )
            for f in fuentes.fragmentos
        ],
        scores=list(fuentes.scores),
    )
