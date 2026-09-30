"""Router: doctrina (Plan A — flujo de aprobación y doctrina global).

Endpoints:
- GET  /doctrina/global          — supervisor: pendientes + aprobadas.
- GET  /doctrina/publica         — sidebar derecho: doctrinas globales.
- POST /doctrina/global/cargar   — supervisor: sube y deja directo 'global'.
- POST /doctrina/global/{id}/aprobar  — supervisor: publicado -> global.
- POST /doctrina/global/{id}/rechazar — supervisor: publicado -> rechazado.
- POST /expedientes/{id}/obras/{id}/seleccionar-global — operador: copia.
- POST /doctrina/seleccionar-global-sin-expediente   — operador: copia a consulta.
- POST /obras/{id}/restaurar     — propietario/admin: reactiva soft-delete.
- GET  /expedientes/{id}/doctrina-privada — desplegable chat: privadas.

Permisos: módulo 'doctrina'. Supervisor puede crear/leer/actualizar;
operador puede crear/leer/actualizar (no aprobar). Admin full.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.adapters.http.dependencies import (
    ExpedienteRepoDep,
    NormaRepoDep,
    ObraRepoDep,
    RecomendacionRepoDep,
    get_auth_repo,
    require_permiso,
    require_supervisor,
)
from src.application.observability import get_event_bus
from src.application.observability.doctrina_events import (
    DoctrinaAprobada,
    DoctrinaGlobalCargada,
    DoctrinaPropuesta,
    DoctrinaRechazada,
)
from src.application.ports.auth_repository import AuthRepository
from src.domain.entities.usuario import Usuario

router = APIRouter(prefix="/doctrina", tags=["doctrina"])


class CriterioDTO(BaseModel):
    id: int
    nombre_archivo: str
    contenido_texto: str
    procedencia: str | None = None
    recomendada: bool
    updated_at: str | None = None


class CriterioPatchBody(BaseModel):
    contenido_texto: str | None = None
    procedencia: str | None = None
    recomendada: bool | None = None


@router.get(
    "/criterios",
    response_model=list[CriterioDTO],
    summary="Listar criterios (solo admin)",
)
async def get_criterios(
    current_user: Annotated[Usuario, Depends(require_permiso("criterios", "leer"))],
    obra_repo: ObraRepoDep,
) -> list[CriterioDTO]:
    """Lista los criterios indexados (`tipo_documento='criterio'`)."""
    criterios = await obra_repo.listar_criterios()
    return [
        CriterioDTO(
            id=c.id or 0,
            nombre_archivo=c.nombre_archivo,
            contenido_texto=c.contenido_texto,
            procedencia=c.procedencia,
            recomendada=c.recomendada,
            updated_at=c.created_at.isoformat() if c.created_at else None,
        )
        for c in criterios
    ]


@router.patch(
    "/criterios/{obra_id}",
    response_model=CriterioDTO,
    summary="Editar criterio (solo admin)",
)
async def patch_criterio(
    obra_id: int,
    body: CriterioPatchBody,
    current_user: Annotated[Usuario, Depends(require_permiso("criterios", "actualizar"))],
    obra_repo: ObraRepoDep,
) -> CriterioDTO:
    """Edita texto/metadatos de un criterio."""
    actualizado = await obra_repo.actualizar_criterio(
        obra_id=obra_id,
        contenido_texto=body.contenido_texto,
        procedencia=body.procedencia,
        recomendada=body.recomendada,
    )
    if actualizado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Criterio id={obra_id} no encontrado.",
        )
    return CriterioDTO(
        id=actualizado.id or 0,
        nombre_archivo=actualizado.nombre_archivo,
        contenido_texto=actualizado.contenido_texto,
        procedencia=actualizado.procedencia,
        recomendada=actualizado.recomendada,
        updated_at=actualizado.created_at.isoformat() if actualizado.created_at else None,
    )


class ObraGlobalDTO(BaseModel):
    id: int
    nombre_archivo: str
    autor: str | None = None
    autor_instancia: str | None = None
    procedencia: str | None = None
    fecha_documento: str | None = None
    estado_visibilidad: str
    recomendada: bool
    motivo_rechazo: str | None = None
    created_at_iso: str | None = None
    # Puntero N2/N3 (None = pieza propia con archivo/contenido).
    corpus: str | None = None
    corpus_ref: str | None = None


class RechazarBody(BaseModel):
    motivo: str = Field(..., min_length=1, max_length=500)


class SeleccionarGlobalResp(BaseModel):
    obra_id: int
    estado_visibilidad: str


class DoctrinaMiaDTO(BaseModel):
    """Doctrina propia del usuario (Plan C) o de revisión (supervisor)."""

    id: int
    expediente_id: int | None = None
    numero_caso: str | None = None
    tipo_documento: str
    nombre_archivo: str
    autor: str | None = None
    autor_instancia: str | None = None
    procedencia: str | None = None
    fecha_documento: str | None = None
    estado_visibilidad: str
    estado_procesamiento: str
    recomendada: bool
    es_global: bool
    motivo_rechazo: str | None = None
    created_at_iso: str | None = None


class RecomendarBody(BaseModel):
    obra_global_id: int | None = None
    expediente_id: int
    # Alternativa por corpus N2/N3 (abreviatura norma global).
    corpus: str | None = None
    corpus_ref: str | None = None


class RecomendacionDTO(BaseModel):
    id: int
    obra_global_id: int | None = None
    nombre_archivo: str
    expediente_id: int
    recomendado_por: int
    recomendado_por_nombre: str | None = None
    recomendado_por_cargo: str | None = None
    estado: str
    motivo_rechazo: str | None = None
    created_at_iso: str | None = None
    corpus: str | None = None
    corpus_ref: str | None = None


class AprobarRecomendacionResp(BaseModel):
    recomendacion_id: int
    estado: str


@router.get(
    "/expedientes/{expediente_id}/doctrina-privada",
    response_model=list[ObraGlobalDTO],
    summary="Doctrina privada del expediente (desplegable del chat)",
)
async def get_doctrina_privada_expediente(
    expediente_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("doctrina", "leer"))],
    obra_repo: ObraRepoDep,
) -> list[ObraGlobalDTO]:
    """Doctrinas privadas/publicadas del expediente para el desplegable del chat."""
    obras = await obra_repo.listar_doctrina_privada(expediente_id, current_user.id)
    return [
        ObraGlobalDTO(
            id=o.id or 0,
            nombre_archivo=o.nombre_archivo,
            autor=o.autor,
            autor_instancia=o.autor_instancia,
            procedencia=o.procedencia,
            fecha_documento=o.fecha_documento,
            estado_visibilidad=o.estado_visibilidad,
            recomendada=o.recomendada,
            corpus=o.corpus,
            corpus_ref=o.corpus_ref,
            created_at_iso=o.created_at.isoformat() if o.created_at else None,
        )
        for o in obras
    ]


async def _dto_mia(
    obra,
    expediente_repo,
    numeros_caso: dict[int, str | None] | None = None,
) -> DoctrinaMiaDTO:
    """Serializa una Obra a DoctrinaMiaDTO, resolviendo numero_caso si aplica.

    `numeros_caso` es una cache por peticion {expediente_id: numero_caso}: en una
    lista, cada expediente se consulta una sola vez en vez de una vez por obra.
    """
    numero_caso: str | None = None
    if obra.expediente_id is not None and expediente_repo is not None:
        if numeros_caso is not None and obra.expediente_id in numeros_caso:
            numero_caso = numeros_caso[obra.expediente_id]
        else:
            exp = await expediente_repo.obtener(obra.expediente_id)
            numero_caso = exp.numero_caso if exp else None
            if numeros_caso is not None:
                numeros_caso[obra.expediente_id] = numero_caso
    return DoctrinaMiaDTO(
        id=obra.id or 0,
        expediente_id=obra.expediente_id,
        numero_caso=numero_caso,
        tipo_documento=obra.tipo_documento,
        nombre_archivo=obra.nombre_archivo,
        autor=obra.autor,
        autor_instancia=obra.autor_instancia,
        procedencia=obra.procedencia,
        fecha_documento=obra.fecha_documento,
        estado_visibilidad=obra.estado_visibilidad,
        estado_procesamiento=obra.estado_procesamiento,
        recomendada=obra.recomendada,
        es_global=obra.estado_visibilidad == "global",
        motivo_rechazo=obra.motivo_rechazo,
        created_at_iso=obra.created_at.isoformat() if obra.created_at else None,
    )


# --- Recomendación de doctrina global por expediente (Plan) ---


async def _recomendacion_dto(rec, nombre_archivo: str, autor) -> RecomendacionDTO:
    """Serializa una RecomendacionDoctrina a DTO con datos del autor."""
    return RecomendacionDTO(
        id=rec.id or 0,
        obra_global_id=rec.obra_global_id,
        nombre_archivo=nombre_archivo,
        expediente_id=rec.expediente_id,
        recomendado_por=rec.recomendado_por,
        recomendado_por_nombre=autor.nombre if autor else None,
        recomendado_por_cargo=autor.cargo if autor else None,
        estado=rec.estado,
        motivo_rechazo=rec.motivo_rechazo,
        created_at_iso=rec.created_at.isoformat() if rec.created_at else None,
        corpus=rec.corpus,
        corpus_ref=rec.corpus_ref,
    )


async def _recomendacion_dto_completo(
    rec, obra_repo, auth_repo, norma_repo=None
) -> RecomendacionDTO:
    """Resuelve nombre de la obra o norma y datos del que recomendó."""
    if rec.obra_global_id is None and norma_repo is not None and rec.corpus_ref:
        norma = await norma_repo.get_by_abreviatura(rec.corpus_ref)
        nombre = norma.nombre if norma else rec.corpus_ref
    else:
        global_ = (
            await obra_repo.obtener_global(rec.obra_global_id)
            if rec.obra_global_id is not None
            else None
        )
        nombre = (
            global_.nombre_archivo if global_ else f"obra#{rec.obra_global_id or rec.corpus_ref}"
        )
    autor = await auth_repo.get_by_id(rec.recomendado_por) if auth_repo else None
    return await _recomendacion_dto(rec, nombre, autor)


@router.post(
    "/recomendar",
    response_model=RecomendacionDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Recomendar doctrina global a un expediente",
)
async def post_recomendar(
    body: RecomendarBody,
    current_user: Annotated[Usuario, Depends(require_permiso("doctrina", "actualizar"))],
    obra_repo: ObraRepoDep,
    recomendacion_repo: RecomendacionRepoDep,
    expediente_repo: ExpedienteRepoDep,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    norma_repo: NormaRepoDep,
) -> RecomendacionDTO:
    """Marca una doctrina GLOBAL o un ítem de corpus N2/N3 como recomendado.

    - Supervisor: auto-aprueba (estado 'recomendada').
    - Operador: propone (estado 'pendiente'); el supervisor aprueba luego.
    Valida: la obra es global activa O la norma N2/N3 existe y está
    indexada; el expediente es visible (activo).
    """
    por_corpus = body.obra_global_id is None
    if por_corpus and not (body.corpus and body.corpus_ref):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Sin obra_global_id se requiere corpus + corpus_ref.",
        )
    if not por_corpus and (body.corpus or body.corpus_ref):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="obra_global_id y corpus/corpus_ref son excluyentes.",
        )

    nombre_item: str
    if por_corpus:
        assert body.corpus_ref is not None
        norma = await norma_repo.get_by_abreviatura(body.corpus_ref)
        # Se recomienda lo global (normas, jurisprudencia o doctrina); una fuente
        # privada, pendiente o rechazada no llega a otros usuarios.
        if norma is None or norma.estado_visibilidad != "global":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ítem de corpus '{body.corpus_ref}' no encontrado.",
            )
        nombre_item = norma.nombre
    else:
        # Verificar que la obra sea una doctrina global activa.
        assert body.obra_global_id is not None
        global_ = await obra_repo.obtener_global(body.obra_global_id)
        if global_ is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Doctrina global id={body.obra_global_id} no encontrada.",
            )
        nombre_item = global_.nombre_archivo

    # Verificar que el expediente exista y esté activo (visible).
    expediente = await expediente_repo.obtener(body.expediente_id)
    if expediente is None or expediente.estado != "activo":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expediente id={body.expediente_id} no encontrado o no activo.",
        )

    # Supervisor auto-aprueba; operador propone (pendiente).
    es_supervisor = current_user.rol == "supervisor"
    estado = "recomendada" if es_supervisor else "pendiente"

    rec = await recomendacion_repo.recomendar(
        obra_global_id=body.obra_global_id,
        expediente_id=body.expediente_id,
        recomendado_por=current_user.id,
        estado=estado,
        corpus=body.corpus,
        corpus_ref=body.corpus_ref,
    )
    # Supervisor: `recomendar` ya creó la recomendación en estado
    # 'recomendada' (auto-aprueba). No llamar a `aprobar` (busca pendiente).

    autor = await auth_repo.get_by_id(current_user.id)
    return await _recomendacion_dto(rec, nombre_item, autor)


@router.get(
    "/expedientes/{expediente_id}/recomendadas",
    response_model=list[RecomendacionDTO],
    summary="Doctrinas recomendadas para un expediente (aprobadas)",
)
async def get_recomendadas_expediente(
    expediente_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("doctrina", "leer"))],
    recomendacion_repo: RecomendacionRepoDep,
    obra_repo: ObraRepoDep,
    expediente_repo: ExpedienteRepoDep,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    norma_repo: NormaRepoDep,
) -> list[RecomendacionDTO]:
    """Lista las doctrinas globales recomendadas (aprobadas) para un expediente."""
    expediente = await expediente_repo.obtener(expediente_id)
    if expediente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expediente id={expediente_id} no encontrado.",
        )
    recs = await recomendacion_repo.listar_por_expediente(expediente_id)
    return [await _recomendacion_dto_completo(r, obra_repo, auth_repo, norma_repo) for r in recs]


@router.get(
    "/recomendaciones/pendientes",
    response_model=list[RecomendacionDTO],
    summary="Recomendaciones pendientes de aprobación (supervisor)",
)
async def get_recomendaciones_pendientes(
    current_user: Annotated[Usuario, Depends(require_supervisor)],
    recomendacion_repo: RecomendacionRepoDep,
    obra_repo: ObraRepoDep,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    norma_repo: NormaRepoDep,
) -> list[RecomendacionDTO]:
    """Lista las recomendaciones pendientes de aprobación (operadores)."""
    recs = await recomendacion_repo.listar_pendientes()
    return [await _recomendacion_dto_completo(r, obra_repo, auth_repo, norma_repo) for r in recs]


@router.post(
    "/recomendaciones/{recomendacion_id}/aprobar",
    response_model=AprobarRecomendacionResp,
    summary="Aprobar recomendación (supervisor)",
)
async def post_aprobar_recomendacion(
    recomendacion_id: int,
    current_user: Annotated[Usuario, Depends(require_supervisor)],
    recomendacion_repo: RecomendacionRepoDep,
) -> AprobarRecomendacionResp:
    aprobada = await recomendacion_repo.aprobar(recomendacion_id, current_user.id)
    if aprobada is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recomendación id={recomendacion_id} no encontrada o no pendiente.",
        )
    return AprobarRecomendacionResp(
        recomendacion_id=aprobada.id,  # type: ignore[arg-type]
        estado=aprobada.estado,
    )


@router.post(
    "/recomendaciones/{recomendacion_id}/rechazar",
    response_model=AprobarRecomendacionResp,
    summary="Rechazar recomendación (supervisor)",
)
async def post_rechazar_recomendacion(
    recomendacion_id: int,
    body: RechazarBody,
    current_user: Annotated[Usuario, Depends(require_supervisor)],
    recomendacion_repo: RecomendacionRepoDep,
) -> AprobarRecomendacionResp:
    rechazada = await recomendacion_repo.rechazar(recomendacion_id, current_user.id, body.motivo)
    if rechazada is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recomendación id={recomendacion_id} no encontrada o no pendiente.",
        )
    return AprobarRecomendacionResp(
        recomendacion_id=rechazada.id,  # type: ignore[arg-type]
        estado=rechazada.estado,
    )


@router.post(
    "/recomendaciones/aprobar-todas",
    response_model=dict,
    summary="Aprobar todas las recomendaciones pendientes (supervisor)",
)
async def post_aprobar_todas_recomendaciones(
    current_user: Annotated[Usuario, Depends(require_supervisor)],
    recomendacion_repo: RecomendacionRepoDep,
    ids: list[int] | None = Body(None),
) -> dict:
    """Aprobar en lote. Si `ids` viene, aprueba solo esas (Seleccionar);
    si no, aprueba todas las pendientes (Seleccionar todo)."""
    count = await recomendacion_repo.aprobar_todas(current_user.id, ids=ids)
    return {"aprobadas": count}


@router.get("/obras/{obra_id}/descargar", response_model=None)
async def get_descargar_obra(
    obra_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("doctrina", "leer"))],
    obra_repo: ObraRepoDep,
) -> FileResponse | StreamingResponse:
    """Descarga el archivo original de una doctrina/criterio/obra.

    - Si `ruta_archivo` apunta al vault o al storage de uploads -> sirve ese
      archivo con su tipo real.
    - Si solo hay `contenido_texto` -> genera un .txt con el texto.
    """
    obra = await obra_repo.obtener(obra_id, current_user.id)
    if obra is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Obra id={obra_id} no encontrada.",
        )
    # Punteros N2/N3 no tienen archivo ni contenido: son referencias al
    # corpus (se consultan, no se descargan). 404 honesto, no .txt vacío.
    if obra.corpus_ref:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{obra.nombre_archivo}' es una referencia a "
                f"{obra.corpus_ref}: se consulta en el chat, no se descarga."
            ),
        )

    ruta = Path(obra.ruta_archivo) if obra.ruta_archivo else None
    if ruta is not None and ruta.exists():
        return FileResponse(
            str(ruta),
            filename=obra.nombre_archivo,
            media_type="application/octet-stream",
        )

    # Sin archivo físico: servir el contenido_texto como .txt.
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        obra.contenido_texto,
        headers={"Content-Disposition": f'attachment; filename="{obra.nombre_archivo}.txt"'},
    )


@router.get("/events")
async def doctrina_events_sse(
    current_user: Annotated[Usuario, Depends(require_supervisor)],
    request: Request,
) -> StreamingResponse:
    """SSE stream de eventos de doctrina en vivo (supervisor).

    Eventos: DoctrinaPropuesta, DoctrinaAprobada, DoctrinaRechazada,
    DoctrinaGlobalCargada.
    Formato: data: {json}\n\n (SSE estándar).
    """
    bus = get_event_bus()

    async def event_generator():
        async for evento in bus.subscribe():
            if not isinstance(
                evento,
                (DoctrinaPropuesta, DoctrinaAprobada, DoctrinaRechazada, DoctrinaGlobalCargada),
            ):
                continue
            data = {
                "tipo": type(evento).__name__,
                "obra_id": evento.obra_id,
                "usuario_id": evento.usuario_id,
                "usuario_nombre": evento.usuario_nombre,
                "nombre_archivo": evento.nombre_archivo,
                "expediente_id": getattr(evento, "expediente_id", None),
                "motivo": getattr(evento, "motivo", None),
                "timestamp_ms": evento.timestamp_ms,
            }
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
