"""Router de gestion de expedientes (Sprint 4 — HU-13..HU-15).

Endpoints:
  POST /expedientes/                                  — Abrir expediente (supervisor)
  GET  /expedientes/                                  — Listar expedientes propios
  POST /expedientes/{expediente_id}/obras             — Cargar obra (PDF/Word)
  POST /expedientes/{expediente_id}/obras/publicar    — Publicar obra (Regla 5: dueno)
  GET  /expedientes/{expediente_id}/historial         — Listar obras (Regla 5: aplica adapter)

Seguridad:
- require_supervisor para POST /expedientes/ (Decision: supervisor abre casos).
- require_consulta_user para el resto (supervisor + operador cargan obras).
- usuario_id SIEMPRE del JWT (current_user.id), no del body (Regla 4).
- Regla 5 (BLOQUEANTE): el filtro de visibilidad vive en el adapter
  ObraRepoImpl — el use case solo pasa usuario_id. Tests deben verificar
  que Operador A no ve obras privadas de Operador B en mismo expediente.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from src.adapters.http.dependencies import (
    AuditLogRepoDep,
    EmbedderDep,
    ExpedienteRepoDep,
    FragmentoRepoDep,
    ObraRepoDep,
    TextExtractorDep,
    ValidadorDep,
    VectorRepoDep,
    get_auth_repo,
    require_permiso,
    require_supervisor,
)
from src.adapters.http.upload import leer_upload
from src.application.admin.audit import registrar_auditoria
from src.application.expedientes.abrir import (
    AbrirExpediente,
    AbrirExpedienteRequest,
    AbrirExpedienteResponse,
    NumeroCasoDuplicadoError,
)
from src.application.expedientes.cargar_obra import (
    CargaObraExtraccionError,
    CargaObraValidacionError,
    CargarObra,
    CargarObraRequest,
    CargarObraResponse,
)
from src.application.expedientes.eliminar_expediente import eliminar_expediente
from src.application.expedientes.eliminar_obra import (
    ObraNoEncontradaError,
    eliminar_obra,
)
from src.application.expedientes.eliminar_obra import (
    ObraNoPropiaError as EliminarObraNoPropiaError,
)
from src.application.expedientes.indexar_obra import IndexarObra
from src.application.expedientes.listar_historial import (
    ListarHistorialExpediente,
    ListarHistorialRequest,
    ListarHistorialResponse,
    ObraResumenDTO,
)
from src.application.expedientes.promover_obra import (
    ObraNoPromovibleError,
    PromoverObra,
)
from src.application.expedientes.publicar_obra import (
    ObraNoPropiaError,
    PublicarObra,
    PublicarObraRequest,
    PublicarObraResponse,
)
from src.application.ports.auth_repository import AuthRepository
from src.config import get_settings
from src.domain.entities.usuario import Usuario
from src.domain.services.evaluador_requisitos import REQUISITOS, faltantes, nombres_legibles
from src.domain.services.validador_upload import UploadInvalidoError

router = APIRouter(prefix="/expedientes", tags=["expedientes"])


class RequisitosResp(BaseModel):
    """Requisitos de entrada por tipo de caso (vault sin sprints)."""

    tipo_proceso: str
    requeridos: list[str]
    nombres: list[str]


class PromocionResp(BaseModel):
    obra_id: int
    tipo_documento: str
    estado_validacion: str | None


class PromocionPendienteResp(BaseModel):
    obra_id: int
    expediente_id: int | None
    propietario_id: int
    nombre_archivo: str
    tipo_documento: str


class ResolverPromocionBody(BaseModel):
    aprobar: bool
    motivo: str | None = Field(default=None, max_length=500)


@router.get(
    "/promociones-pendientes",
    response_model=list[PromocionPendienteResp],
    summary="Obrados propuestos para promoverse a jurisprudencia (supervisor)",
)
async def get_promociones_pendientes(
    _supervisor: Annotated[Usuario, Depends(require_supervisor)],
    obra_repo: ObraRepoDep,
) -> list[PromocionPendienteResp]:
    """Cola de aprobación: obrados con `estado_validacion='promocion_pendiente'`."""
    return [
        PromocionPendienteResp(
            obra_id=o.id,  # type: ignore[arg-type]
            expediente_id=o.expediente_id,
            propietario_id=o.propietario_id,
            nombre_archivo=o.nombre_archivo,
            tipo_documento=o.tipo_documento,
        )
        for o in await obra_repo.listar_promociones_pendientes()
    ]


@router.get(
    "/requisitos",
    response_model=RequisitosResp,
    summary="Requisitos de obrados por tipo de caso (para alert en apertura)",
)
async def get_requisitos(
    tipo_proceso: str = Query(pattern="^(consulta|apelacion_incidental|apelacion_restringida)$"),
) -> RequisitosResp:
    """Lista piezas de entrada obligatorias según taxonomía (sin crear nada)."""
    req = REQUISITOS[tipo_proceso]
    return RequisitosResp(
        tipo_proceso=tipo_proceso,
        requeridos=sorted(req),
        nombres=nombres_legibles(req),
    )


class RequisitosFaltantesResp(BaseModel):
    """Faltantes institucionales de un expediente (usa tipos_activos sin Regla 5)."""

    expediente_id: int
    tipo_proceso: str
    completo: bool
    faltantes: list[str]
    nombres: list[str]


@router.get(
    "/{expediente_id}/requisitos-faltantes",
    response_model=RequisitosFaltantesResp,
    summary="Faltantes institucionales del expediente (para aviso en chat)",
)
async def get_requisitos_faltantes(
    expediente_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("expedientes", "leer"))],
    expediente_repo: ExpedienteRepoDep,
    obra_repo: ObraRepoDep,
) -> RequisitosFaltantesResp:
    """Faltantes de obrados para el expediente (conteo institucional, sin Regla 5).

    Usa tipos_activos_por_expediente (todas las obras activas) para que el
    aviso coincida exactamente con el guard de generación de borradores.
    """
    expediente = await expediente_repo.obtener(expediente_id)
    if expediente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expediente id={expediente_id} no existe.",
        )
    if hasattr(obra_repo, "tipos_activos_por_expediente"):
        tipos = await obra_repo.tipos_activos_por_expediente(expediente_id)  # type: ignore[attr-defined]
    else:
        obras = await obra_repo.listar_por_expediente(expediente_id, current_user.id)
        tipos = {o.tipo_documento for o in obras}
    falt = faltantes(expediente.tipo_proceso, tipos)
    return RequisitosFaltantesResp(
        expediente_id=expediente_id,
        tipo_proceso=expediente.tipo_proceso,
        completo=len(falt) == 0,
        faltantes=sorted(falt),
        nombres=nombres_legibles(falt),
    )


# ----- DTOs -----


class AbrirExpedienteBody(BaseModel):
    """Body POST /expedientes/."""

    numero_caso: str = Field(min_length=1, max_length=64)
    tipo_proceso: str = Field(pattern="^(consulta|apelacion_incidental|apelacion_restringida)$")
    tribunal_origen: str = Field(min_length=1)
    procesado_nombre: str = Field(min_length=1)
    delito: str = Field(min_length=1)
    procesado_grado: str | None = None
    sentencia_origen: str | None = None
    fojas_total: int | None = Field(default=None, ge=0)


class EditarExpedienteBody(BaseModel):
    """Body PATCH /expedientes/{id}.

    Todos los campos opcionales. Un string vacío se ignora (no actualiza):
    el frontend filtra '' antes de enviar, pero el backend tambien lo tolera
    para no romper con clientes que envien el form completo.
    """

    numero_caso: str | None = Field(default=None, max_length=64)
    tipo_proceso: str | None = Field(
        default=None, pattern="^(consulta|apelacion_incidental|apelacion_restringida)$"
    )
    tribunal_origen: str | None = None
    procesado_nombre: str | None = None
    delito: str | None = None


class AbrirExpedienteResp(BaseModel):
    """Response POST /expedientes/."""

    expediente_id: int
    numero_caso: str
    estado: str
    creado_at_iso: str


class ObraCargadaResp(BaseModel):
    """Response POST /expedientes/{id}/obras."""

    obra_id: int
    estado_visibilidad: str
    estado_procesamiento: str
    created_at_iso: str


class PublicarObraResp(BaseModel):
    """Response POST /expedientes/{id}/obras/publicar."""

    obra_id: int
    estado_visibilidad: str


class ExpedienteResumenDTO(BaseModel):
    """DTO resumen de un expediente para listado."""

    id: int
    numero_caso: str
    tipo_proceso: str
    estado: str
    tribunal_origen: str
    procesado_nombre: str
    delito: str
    fojas_total: int | None
    abierto_por: int
    created_at: str | None


class PaginaExpedientesResp(BaseModel):
    """Lista paginada de expedientes propios."""

    items: list[ExpedienteResumenDTO]
    total: int
    pagina: int
    por_pagina: int


class PaginaObrasHistorialResp(BaseModel):
    """Response GET /expedientes/{id}/historial."""

    expediente_id: int
    obras: list[ObraResumenDTO]
    total: int


# ----- Endpoints -----


@router.post(
    "/",
    response_model=AbrirExpedienteResp,
    status_code=status.HTTP_201_CREATED,
    summary="Abrir un expediente procesal (solo supervisor)",
)
async def post_abrir(
    body: AbrirExpedienteBody,
    current_user: Annotated[Usuario, Depends(require_permiso("expedientes", "crear"))],
    expediente_repo: ExpedienteRepoDep,
    audit_repo: AuditLogRepoDep,
) -> AbrirExpedienteResp:
    """Abre un nuevo expediente. Solo supervisor.

    Raises:
        409: numero_caso duplicado.
        422: tipo_proceso fuera de CHECK constraint.
    """
    uc = AbrirExpediente(expediente_repo)
    try:
        resultado: AbrirExpedienteResponse = await uc.ejecutar(
            AbrirExpedienteRequest(
                numero_caso=body.numero_caso,
                tipo_proceso=body.tipo_proceso,
                tribunal_origen=body.tribunal_origen,
                procesado_nombre=body.procesado_nombre,
                delito=body.delito,
                abierto_por=current_user.id,
                procesado_grado=body.procesado_grado,
                sentencia_origen=body.sentencia_origen,
                fojas_total=body.fojas_total,
            )
        )
    except NumeroCasoDuplicadoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # R6: abrir expediente es accion sensitiva (append-only, no rompe el flujo).
    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="crear_expediente",
            usuario_id=current_user.id,
            entidad="expediente",
            entidad_id=resultado.expediente_id,
            detalle={"numero_caso": body.numero_caso},
        )

    return AbrirExpedienteResp(
        expediente_id=resultado.expediente_id,
        numero_caso=resultado.numero_caso,
        estado=resultado.estado,
        creado_at_iso=resultado.creado_at_iso,
    )


@router.delete(
    "/{expediente_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar expediente (soft delete: archivar, CRITICAL #3)",
)
async def delete_expediente(
    expediente_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("expedientes", "eliminar"))],
    expediente_repo: ExpedienteRepoDep,
    audit_repo: AuditLogRepoDep,
) -> None:
    """Soft delete: estado='archivado' (no borra obras ni borradores).

    Registra la accion en audit_log (Trail of Bits R6).

    Raises:
        404: expediente inexistente o ya archivado.
    """
    eliminado = await eliminar_expediente(expediente_repo, expediente_id=expediente_id)
    if not eliminado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expediente no encontrado.",
        )

    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="eliminar_expediente",
            usuario_id=current_user.id,
            entidad="expediente",
            entidad_id=expediente_id,
        )


@router.get(
    "/",
    response_model=PaginaExpedientesResp,
    summary="Listar expedientes del usuario autenticado",
)
async def get_listar(
    current_user: Annotated[Usuario, Depends(require_permiso("expedientes", "leer"))],
    expediente_repo: ExpedienteRepoDep,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    estado: str | None = Query(None, pattern="^(activo|archivado)$"),
) -> PaginaExpedientesResp:
    """Lista expedientes visibles para el usuario (Plan: expedientes compartidos).

    - Supervisor: ve todos (activos + archivados).
    - Operador: ve solo los activos (los que el supervisor abrió).
    Restaura el fix #322 (los operadores veían solo sus propios expedientes).
    """
    es_supervisor = current_user.rol == "supervisor"
    items, total = await expediente_repo.listar_todos(
        incluir_archivados=es_supervisor,
        estado=estado,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    return PaginaExpedientesResp(
        items=[
            ExpedienteResumenDTO(
                id=e.id,  # type: ignore[arg-type]
                numero_caso=e.numero_caso,
                tipo_proceso=e.tipo_proceso,
                estado=e.estado,
                tribunal_origen=e.tribunal_origen,
                procesado_nombre=e.procesado_nombre,
                delito=e.delito,
                fojas_total=e.fojas_total,
                abierto_por=e.abierto_por,
                created_at=e.created_at.isoformat() if e.created_at else None,
            )
            for e in items
        ],
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
    )


@router.post(
    "/{expediente_id}/obras",
    response_model=ObraCargadaResp,
    status_code=status.HTTP_201_CREATED,
    summary="Cargar obra (PDF/Word) al expediente",
)
async def post_cargar_obra(
    expediente_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("obras", "crear"))],
    expediente_repo: ExpedienteRepoDep,
    obra_repo: ObraRepoDep,
    fragmento_repo: FragmentoRepoDep,
    vector_repo: VectorRepoDep,
    embedder: EmbedderDep,
    text_extractor: TextExtractorDep,
    validador: ValidadorDep,
    audit_repo: AuditLogRepoDep,
    file: UploadFile,
    tipo_documento: str = Form(
        ...,
        pattern="^(sentencia|memorial_apelacion|auto_interlocutorio|"
        "oficio_elevacion|acta_audiencia|requerimiento_fiscal|"
        "dictamen_radicatoria|dictamen_fondo|relacion_obrados|"
        "proyecto_auto_vista|auto_vista|otro)$",
    ),
    fojas_inicio: int | None = Form(None, ge=0),
    fojas_fin: int | None = Form(None, ge=0),
    autor_instancia: str | None = Form(None, max_length=100),
) -> ObraCargadaResp:
    """Sube un PDF/Word al expediente, extrae texto y persiste Obra.

    Regla 5 Trail of Bits:
    - Validacion upload: nombre + extension + Content-Type + magic bytes
      + size 500MB (ValidadorUpload).
    - Extraccion aislada del event loop (thread para PDF nativo/DOCX; subprocess
      dedicado solo para OCR de escaneados).
    - Fallo validacion o extraccion → 422 limpio (no 500).
    """
    data = await leer_upload(file)
    filename = file.filename or "documento"
    content_type = file.content_type or "application/octet-stream"

    # Verificar expediente existe antes de cargar obra
    expediente = await expediente_repo.obtener(expediente_id)
    if expediente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expediente id={expediente_id} no existe.",
        )

    # Configurar storage_path desde settings
    settings = get_settings()
    storage_path = Path(settings.upload_dir)

    uc = CargarObra(
        validador_upload=validador,
        text_extractor=text_extractor,
        obra_repo=obra_repo,
        storage_path=storage_path,
    )
    try:
        resultado: CargarObraResponse = await uc.ejecutar(
            CargarObraRequest(
                expediente_id=expediente_id,
                propietario_id=current_user.id,
                filename=filename,
                content_type=content_type,
                contenido_bytes=data,
                tipo_documento=tipo_documento,
                fojas_inicio=fojas_inicio,
                fojas_fin=fojas_fin,
                autor_instancia=autor_instancia,
            )
        )
    except CargaObraValidacionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except UploadInvalidoError as exc:
        # Seguridad: el validador puede lanzar directo si no se wrapping.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except CargaObraExtraccionError as exc:
        # Regla 5: fallo extraccion → 422 limpio.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    obra = await obra_repo.obtener(resultado.obra_id, current_user.id)
    if obra is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La obra se guardó, pero no pudo recuperarse para indexación.",
        )

    await obra_repo.actualizar_estado_procesamiento(resultado.obra_id, "pendiente")
    try:
        indexado = await IndexarObra(
            obra_repo=obra_repo,
            fragmento_repo=fragmento_repo,
            embedder=embedder,
            vector_repo=vector_repo,
        ).ejecutar(obra)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"La obra se cargó, pero no pudo indexarse: {exc}",
        ) from exc

    # Trail of Bits R6: la carga de obrados alimenta el RAG del caso.
    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="cargar_obra",
            usuario_id=current_user.id,
            entidad="obra",
            entidad_id=resultado.obra_id,
            detalle={
                "expediente_id": expediente_id,
                "tipo_documento": tipo_documento,
                "filename": filename,
            },
        )

    return ObraCargadaResp(
        obra_id=indexado.obra_id,
        estado_visibilidad=obra.estado_visibilidad,
        estado_procesamiento="completado",
        created_at_iso=resultado.created_at_iso,
    )


@router.post(
    "/{expediente_id}/obras/{obra_id}/publicar",
    response_model=PublicarObraResp,
    summary="Publicar obra (privado -> publicado)",
)
async def post_publicar_obra(
    expediente_id: int,
    obra_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("obras", "actualizar"))],
    obra_repo: ObraRepoDep,
    vector_repo: VectorRepoDep,
) -> PublicarObraResp:
    """Publica una obra (Regla 5: solo el dueno).

    Raises:
        403: usuario no es propietario de la obra.
    """
    uc = PublicarObra(obra_repo, vector_repo)
    try:
        resultado: PublicarObraResponse = await uc.ejecutar(
            PublicarObraRequest(obra_id=obra_id, propietario_id=current_user.id)
        )
    except ObraNoPropiaError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return PublicarObraResp(
        obra_id=resultado.obra_id,
        estado_visibilidad=resultado.estado_visibilidad,
    )


@router.post(
    "/{expediente_id}/obras/{obra_id}/proponer-promocion",
    response_model=PromocionResp,
    summary="Proponer que un obrado publicado pase a jurisprudencia (propietario)",
)
async def post_proponer_promocion(
    expediente_id: int,
    obra_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("obras", "actualizar"))],
    obra_repo: ObraRepoDep,
    vector_repo: VectorRepoDep,
    audit_repo: AuditLogRepoDep,
) -> PromocionResp:
    """El propietario propone; queda pendiente hasta que el supervisor la resuelva."""
    uc = PromoverObra(obra_repo, vector_repo)
    try:
        obra = await uc.proponer(obra_id=obra_id, usuario_id=current_user.id)
    except ObraNoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ObraNoPromovibleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await registrar_auditoria(
        audit_repo,
        accion="proponer_promocion_obra",
        usuario_id=current_user.id,
        entidad="obra",
        entidad_id=obra_id,
    )
    return PromocionResp(
        obra_id=obra_id, tipo_documento=obra.tipo_documento, estado_validacion="promocion_pendiente"
    )


@router.post(
    "/{expediente_id}/obras/{obra_id}/resolver-promocion",
    response_model=PromocionResp,
    summary="Aprobar o rechazar la promoción de un obrado a jurisprudencia (supervisor)",
)
async def post_resolver_promocion(
    expediente_id: int,
    obra_id: int,
    body: ResolverPromocionBody,
    current_user: Annotated[Usuario, Depends(require_supervisor)],
    obra_repo: ObraRepoDep,
    vector_repo: VectorRepoDep,
    audit_repo: AuditLogRepoDep,
) -> PromocionResp:
    """Aprobar (o promover directamente un obrado publicado) o rechazar con motivo."""
    uc = PromoverObra(obra_repo, vector_repo)
    try:
        obra = await uc.resolver(
            obra_id=obra_id, aprobar=body.aprobar, actor_id=current_user.id, motivo=body.motivo
        )
    except ObraNoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ObraNoPromovibleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await registrar_auditoria(
        audit_repo,
        accion="aprobar_promocion_obra" if body.aprobar else "rechazar_promocion_obra",
        usuario_id=current_user.id,
        entidad="obra",
        entidad_id=obra_id,
    )
    return PromocionResp(
        obra_id=obra_id,
        tipo_documento=obra.tipo_documento,
        estado_validacion=obra.estado_validacion,
    )


@router.get(
    "/{expediente_id}/historial",
    response_model=PaginaObrasHistorialResp,
    summary="Listar obras del expediente (Regla 5)",
)
async def get_historial(
    expediente_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("expedientes", "leer"))],
    expediente_repo: ExpedienteRepoDep,
    obra_repo: ObraRepoDep,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    solo_propias: bool = Query(False, description="True: vista 'mis obras subidas'"),
) -> PaginaObrasHistorialResp:
    """Lista obras del expediente aplicando Regla 5 (BLOQUEANTE).

    Filtro en adapter:
    `must(expediente_id=X) AND must(propietario_id=user OR visibilidad=publicado)`.
    El usuario nunca ve obras privadas de otros. El use case solo pasa usuario_id.
    """
    expediente = await expediente_repo.obtener(expediente_id)
    if expediente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expediente id={expediente_id} no existe.",
        )

    uc = ListarHistorialExpediente(obra_repo, auth_repo=auth_repo)
    resultado: ListarHistorialResponse = await uc.ejecutar(
        ListarHistorialRequest(
            expediente_id=expediente_id,
            usuario_id=current_user.id,
            solo_propias=solo_propias,
        )
    )
    return PaginaObrasHistorialResp(
        expediente_id=resultado.expediente_id,
        obras=resultado.obras,
        total=resultado.total,
    )


@router.patch(
    "/{expediente_id}",
    response_model=ExpedienteResumenDTO,
    summary="Editar metadatos de un expediente (CRUD-3)",
)
async def patch_expediente(
    expediente_id: int,
    body: EditarExpedienteBody,
    current_user: Annotated[Usuario, Depends(require_permiso("expedientes", "actualizar"))],
    expediente_repo: ExpedienteRepoDep,
    audit_repo: AuditLogRepoDep,
) -> ExpedienteResumenDTO:
    """Modifica metadatos de un expediente (numero_caso, procesado, delito). Solo supervisor."""
    # Strings vacíos = no actualizar (el frontend filtra, pero el backend tolera).
    campos: dict[str, str | None] = {
        "numero_caso": body.numero_caso,
        "procesado_nombre": body.procesado_nombre,
        "delito": body.delito,
        "tribunal_origen": body.tribunal_origen,
        "tipo_proceso": body.tipo_proceso,
    }
    campos = {k: (v.strip() if isinstance(v, str) else v) for k, v in campos.items()}
    campos = {k: v for k, v in campos.items() if v}

    actualizado = await expediente_repo.actualizar(
        expediente_id,
        **campos,
    )
    if actualizado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expediente no encontrado.",
        )

    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="editar_expediente",
            usuario_id=current_user.id,
            entidad="expediente",
            entidad_id=expediente_id,
        )

    return ExpedienteResumenDTO(
        id=actualizado.id,  # type: ignore[arg-type]
        numero_caso=actualizado.numero_caso,
        tipo_proceso=actualizado.tipo_proceso,
        estado=actualizado.estado,
        tribunal_origen=actualizado.tribunal_origen,
        procesado_nombre=actualizado.procesado_nombre,
        delito=actualizado.delito,
        fojas_total=actualizado.fojas_total,
        abierto_por=actualizado.abierto_por,
        created_at=actualizado.created_at.isoformat() if actualizado.created_at else None,
    )


class CambiarEstadoBody(BaseModel):
    """Body PATCH /expedientes/{id}/estado."""

    estado: str = Field(pattern="^(activo|archivado)$")


@router.patch(
    "/{expediente_id}/estado",
    response_model=ExpedienteResumenDTO,
    summary="Cambiar estado de un expediente (activo <-> archivado)",
)
async def patch_estado(
    expediente_id: int,
    body: CambiarEstadoBody,
    current_user: Annotated[Usuario, Depends(require_permiso("expedientes", "actualizar"))],
    expediente_repo: ExpedienteRepoDep,
    audit_repo: AuditLogRepoDep,
) -> ExpedienteResumenDTO:
    """Toggle estado del expediente (soft delete: archivado conserva obras).

    Permiso: actualizar (supervisor tiene _FULL en expedientes).
    """
    actualizado = await expediente_repo.actualizar_estado(expediente_id, body.estado)
    if actualizado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expediente no encontrado.",
        )

    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="cambiar_estado_expediente",
            usuario_id=current_user.id,
            entidad="expediente",
            entidad_id=expediente_id,
            detalle={"estado": body.estado},
        )

    return ExpedienteResumenDTO(
        id=actualizado.id,  # type: ignore[arg-type]
        numero_caso=actualizado.numero_caso,
        tipo_proceso=actualizado.tipo_proceso,
        estado=actualizado.estado,
        tribunal_origen=actualizado.tribunal_origen,
        procesado_nombre=actualizado.procesado_nombre,
        delito=actualizado.delito,
        fojas_total=actualizado.fojas_total,
        abierto_por=actualizado.abierto_por,
        created_at=actualizado.created_at.isoformat() if actualizado.created_at else None,
    )


@router.delete(
    "/{expediente_id}/obras/{obra_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar obra de expediente (CRUD-1)",
)
async def delete_obra(
    expediente_id: int,
    obra_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("obras", "eliminar"))],
    obra_repo: ObraRepoDep,
    fragmento_repo: FragmentoRepoDep,
    vector_repo: VectorRepoDep,
    audit_repo: AuditLogRepoDep,
) -> None:
    """Elimina una obra del expediente, limpiando sus fragmentos y vectores.

    Regla 5: solo el propietario o admin.
    """
    es_admin = current_user.rol == "administrador"
    try:
        await eliminar_obra(
            obra_repo,
            fragmento_repo,
            vector_repo,
            expediente_id=expediente_id,
            obra_id=obra_id,
            solicitante_id=current_user.id,
            es_admin=es_admin,
        )
    except ObraNoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EliminarObraNoPropiaError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="eliminar_obra",
            usuario_id=current_user.id,
            entidad="obra",
            entidad_id=obra_id,
        )
