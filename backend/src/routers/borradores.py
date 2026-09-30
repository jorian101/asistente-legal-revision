"""Router: /borradores — Sprint 6 Generacion de Respuestas Juridicas.

Endpoints:
  POST /borradores/generar         — Stream LLM y persiste borrador/historial
  POST /borradores/{id}/publicar   — Cambia estado a 'publicado' (Regla 7)
  GET  /borradores/                — Lista borradores de un expediente
  GET  /borradores/{id}            — Obtiene un borrador (Regla 7 visibilidad)

Seguridad (Regla 7 Trail of Bits BLOQUEANTE):
- BorradorNoPropioError -> 403 (publicar/obtener borrador ajeno no publicado)
- BorradorVacioError -> 422 (publicar borrador sin contenido generado)
- PlantillaNoImplementadaError -> 422 (dictamen_radicatoria stub)
- ConsultaSinExpedienteError -> 422 (auto_vista_* sin expediente_id)
- require_operador: solo operador_juridico genera/publica (Tabla 12, RF-16/17/19/20/21)
"""

from __future__ import annotations

import contextlib
import io
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.adapters.http.dependencies import (
    AuditLogRepoDep,
    EmbedderDep,
    ExpedienteRepoDep,
    FormatoRepoDep,
    FragmentoRepoDep,
    ObraRepoDep,
    VectorRepoDep,
    get_auth_repo,
    require_permiso,
    require_supervisor,
)
from src.adapters.http.dependencies_borradores import (
    BorradorRepoDep,
    GenerarBorradorDep,
    ListarBorradoresDep,
    ListarMisBorradoresDep,
    ObtenerBorradorDep,
    PublicarBorradorDep,
)
from src.application.admin.audit import registrar_auditoria, registrar_auditoria_segura
from src.application.borradores.eliminar_borrador import eliminar_borrador
from src.application.borradores.exportar_borrador import (
    exportar_borrador_docx as generar_docx,
)
from src.application.borradores.generar_borrador import (
    GenerarBorradorInput,
)
from src.application.borradores.guardar_borrador import (
    ExpedienteObligatorioError,
    TipoNoGeneraBorradorError,
)
from src.application.borradores.guardar_borrador import (
    guardar as guardar_borrador,
)
from src.application.borradores.publicar_borrador import (
    PublicarBorradorRequest,
)
from src.application.ports.auth_repository import AuthRepository
from src.domain.entities.borrador import Borrador
from src.domain.entities.usuario import Usuario
from src.domain.exceptions import (
    BorradorNoPropioError,
    BorradorVacioError,
    ConsultaSinExpedienteError,
    FaltaCompetenciaError,
    PlantillaNoImplementadaError,
    RequisitosIncompletosError,
    VarianteApelacionNoSoportadaError,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/borradores", tags=["borradores"])


# ----- DTOs -----------------------------------------------------------


class GenerarBorradorRequest(BaseModel):
    """Body del POST /borradores/generar."""

    consulta: str = Field(min_length=3, description="Texto de la consulta juridica")
    expediente_id: int | None = Field(
        default=None,
        description="FK del expediente (obligatorio para auto_vista_*)",
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


class EditarBorradorRequest(BaseModel):
    """Body del PATCH /borradores/{id} — dual .md + layout fiel."""

    contenido: str = Field(min_length=1, description="Nuevo contenido .md del borrador")
    layout: list[dict] | None = Field(
        default=None,
        description="Layout fiel por bloque (align/bold/size/font/heading).",
    )


class DesoficializarBody(BaseModel):
    """Body del POST /borradores/{id}/desoficializar."""

    destino: str = Field(pattern="^(pendiente_oficial|publicado|borrador)$")


class BorradorDTO(BaseModel):
    """DTO publico de un Borrador (incluye layout fiel dual)."""

    id: int
    expediente_id: int
    propietario_id: int
    tipo: str
    contenido: str
    estado: str
    plantilla_usada: str | None = None
    chat_id: int | None = None
    mensaje_id: int | None = None
    autor_nombre: str | None = None
    autor_cargo: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    layout: list[dict] | None = None
    razonamiento: str = ""


class PublicarBorradorResponse(BaseModel):
    """DTO respuesta tras publicar."""

    borrador_id: int
    estado: str


class GuardarBorradorRequest(BaseModel):
    """Body del POST /borradores (guardado explicito desde el chat)."""

    consulta: str = Field(min_length=1)
    expediente_id: int
    tipo_respuesta: str
    contenido: str = Field(min_length=1)
    fuentes: dict | None = None
    chat_id: int | None = None
    mensaje_id: int | None = None
    razonamiento: str = Field(
        default="",
        description="Razonamiento nativo del modelo (modo pensar) a persistir.",
    )


# ----- Mappers --------------------------------------------------------


def _to_dto(
    b: Borrador,
    *,
    autor_nombre: str | None = None,
    autor_cargo: str | None = None,
) -> BorradorDTO:
    return BorradorDTO(
        id=b.id,  # type: ignore[arg-type]
        expediente_id=b.expediente_id,
        propietario_id=b.propietario_id,
        tipo=b.tipo,
        contenido=b.contenido,
        estado=b.estado,
        plantilla_usada=b.plantilla_usada,
        chat_id=b.chat_id,
        mensaje_id=b.mensaje_id,
        autor_nombre=autor_nombre,
        autor_cargo=autor_cargo,
        created_at=b.created_at.isoformat() if b.created_at else None,
        updated_at=b.updated_at.isoformat() if b.updated_at else None,
        layout=b.layout,
        razonamiento=b.razonamiento or "",
    )


async def _autor_de(usuario_id: int, auth_repo: AuthRepository) -> tuple[str | None, str | None]:
    """Resuelve (nombre, cargo institucional) del autor de un borrador."""
    if usuario_id is None:
        return None, None
    autor = await auth_repo.get_by_id(usuario_id)
    if autor is None:
        return None, None
    return autor.nombre, autor.cargo


# ----- Endpoints ------------------------------------------------------


@router.post(
    "",
    response_model=BorradorDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Guardar borrador generado en el chat (guardado explicito)",
)
async def guardar_borrador_endpoint(
    body: GuardarBorradorRequest,
    current_user: Annotated[Usuario, Depends(require_permiso("borradores", "crear"))],
    borrador_repo: BorradorRepoDep,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
) -> BorradorDTO:
    """Guarda (o actualiza) el borrador generado en el chat.

    Regla 7: propietario_id viene del JWT. Si el chat ya tiene un borrador
    guardado, actualiza su contenido (boton 'Actualizar mi borrador').
    """
    try:
        borrador = await guardar_borrador(
            borrador_repo,
            propietario_id=current_user.id,
            expediente_id=body.expediente_id,
            tipo_respuesta=body.tipo_respuesta,
            contenido=body.contenido,
            fuentes=body.fuentes,
            chat_id=body.chat_id,
            mensaje_id=body.mensaje_id,
            razonamiento=body.razonamiento,
        )
    except TipoNoGeneraBorradorError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None
    except ExpedienteObligatorioError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None

    nombre, cargo = await _autor_de(current_user.id, auth_repo)
    return _to_dto(borrador, autor_nombre=nombre, autor_cargo=cargo)


@router.get(
    "/mios",
    response_model=list[BorradorDTO],
    status_code=status.HTTP_200_OK,
    summary="Mis borradores (vista tipo Conversaciones)",
)
async def listar_mis_borradores_endpoint(
    current_user: Annotated[Usuario, Depends(require_permiso("borradores", "leer"))],
    mis_borradores: ListarMisBorradoresDep,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
) -> list[BorradorDTO]:
    """Lista todos los borradores del propietario actual (sin exigir expediente)."""
    borradores = await mis_borradores.ejecutar(propietario_id=current_user.id)
    nombre, cargo = await _autor_de(current_user.id, auth_repo)
    return [_to_dto(b, autor_nombre=nombre, autor_cargo=cargo) for b in borradores]


@router.post(
    "/generar",
    status_code=status.HTTP_201_CREATED,
    summary="Generar respuesta juridica (streaming LLM)",
)
async def generar_borrador(
    body: GenerarBorradorRequest,
    current_user: Annotated[Usuario, Depends(require_permiso("borradores", "crear"))],
    generar_uc: GenerarBorradorDep,
) -> StreamingResponse:
    """Genera una respuesta juridica streaming via LLM y persiste borrador.

    El stream es text/plain token por token. Headers X-Borrador-Id y
    X-Borrador-Tipo permiten al frontend trackear el borrador creado
    (None para consulta_simple).

    Raises:
        422: ConsultaSinExpedienteError / PlantillaNoImplementadaError
        404: ValueError (expediente inexistente)
    """
    try:
        result = await generar_uc.ejecutar(
            GenerarBorradorInput(
                consulta=body.consulta,
                usuario_id=current_user.id,
                expediente_id=body.expediente_id,
                chat_id=body.chat_id,
                tipo_forzado=body.tipo_forzado,
                corpus_refs=body.corpus_refs,
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
    except (
        ConsultaSinExpedienteError,
        PlantillaNoImplementadaError,
        FaltaCompetenciaError,
        VarianteApelacionNoSoportadaError,
    ) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        ) from e
    except ValueError as e:
        # Resolvedor lanza ValueError si expediente no existe
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
        "X-Borrador-Id": str(result.borrador_id) if result.borrador_id else "",
        "X-Borrador-Tipo": result.tipo_respuesta,
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        result.stream,
        media_type="text/plain; charset=utf-8",
        status_code=status.HTTP_201_CREATED,
        headers=headers,
    )


@router.post(
    "/{borrador_id}/publicar",
    response_model=PublicarBorradorResponse,
    status_code=status.HTTP_200_OK,
    summary="Publicar borrador (Regla 7)",
)
async def publicar_borrador(
    borrador_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("borradores", "actualizar"))],
    publicar_uc: PublicarBorradorDep,
    audit_repo: AuditLogRepoDep,
) -> PublicarBorradorResponse:
    """Cambia estado 'borrador' -> 'publicado'. Regla 7: solo el propietario.

    Raises:
        403: BorradorNoPropioError (usuario no es propietario o no existe).
        422: BorradorVacioError (borrador sin contenido generado).
    """
    try:
        result = await publicar_uc.ejecutar(
            PublicarBorradorRequest(
                borrador_id=borrador_id,
                propietario_id=current_user.id,
            )
        )
    except BorradorNoPropioError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e
    except BorradorVacioError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        ) from e

    # R6: publicar borrador es accion sensitiva (Regla 7) — append-only.
    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="publicar_borrador",
            usuario_id=current_user.id,
            entidad="borrador",
            entidad_id=borrador_id,
        )

    return PublicarBorradorResponse(borrador_id=result.borrador_id, estado=result.estado)


@router.delete(
    "/{borrador_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar borrador (soft delete, Regla 7)",
)
async def delete_borrador(
    borrador_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("borradores", "eliminar"))],
    borrador_repo: BorradorRepoDep,
    audit_repo: AuditLogRepoDep,
) -> None:
    """Soft delete: activo=False SOLO si es el propietario (Regla 7).

    Conserva la fila para auditoria (no borrado fisico).

    Raises:
        404: borrador inexistente o de otro usuario (sin revelar cual).
    """
    eliminado = await eliminar_borrador(
        borrador_repo,
        borrador_id=borrador_id,
        propietario_id=current_user.id,
    )
    if not eliminado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Borrador no encontrado.",
        )

    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="eliminar_borrador",
            usuario_id=current_user.id,
            entidad="borrador",
            entidad_id=borrador_id,
        )


@router.patch(
    "/{borrador_id}",
    response_model=BorradorDTO,
    status_code=status.HTTP_200_OK,
    summary="Editar contenido de un borrador (Regla 7, CRUD-4)",
)
async def patch_borrador(
    borrador_id: int,
    body: EditarBorradorRequest,
    current_user: Annotated[Usuario, Depends(require_permiso("borradores", "actualizar"))],
    borrador_repo: BorradorRepoDep,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    audit_repo: AuditLogRepoDep,
) -> BorradorDTO:
    """Modifica el contenido (.md) y opcionalmente el layout fiel. Regla 7.

    Bloqueo N4: un borrador oficial no lo edita nadie, ni el supervisor: hay que
    desoficializarlo primero (vuelve a 'pendiente_oficial'), corregirlo y volver a
    oficializarlo, asi el ejemplo global siempre refleja lo oficializado. En
    'pendiente_oficial' (revision) el supervisor puede corregir el contenido.
    """
    vigente = await borrador_repo.obtener_por_id(borrador_id)
    if vigente is not None and vigente.estado == "oficial":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Borrador oficial: desoficializalo primero para poder editarlo.",
        )
    if (
        vigente is not None
        and vigente.estado == "pendiente_oficial"
        and current_user.rol == "supervisor"
    ):
        # Revision del supervisor: corrige el contenido de un borrador ajeno.
        actualizado = await borrador_repo.actualizar_contenido_supervisor(
            borrador_id, contenido=body.contenido, layout=body.layout
        )
    else:
        actualizado = await borrador_repo.actualizar_contenido_propietario(
            borrador_id,
            propietario_id=current_user.id,
            contenido=body.contenido,
            layout=body.layout,
        )
    if actualizado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Borrador no encontrado, no es de tu propiedad o ya fue publicado.",
        )

    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="editar_borrador",
            usuario_id=current_user.id,
            entidad="borrador",
            entidad_id=borrador_id,
        )

    # El autor es el dueño: si un supervisor corrige un obrado ajeno, no pasa a figurar él.
    nombre, cargo = await _autor_de(actualizado.propietario_id, auth_repo)
    return _to_dto(actualizado, autor_nombre=nombre, autor_cargo=cargo)


@router.get(
    "/",
    response_model=list[BorradorDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar borradores de un expediente",
)
async def listar_borradores(
    expediente_id: Annotated[int, Query(description="FK del expediente")],
    current_user: Annotated[Usuario, Depends(require_permiso("borradores", "leer"))],
    listar_uc: ListarBorradoresDep,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
) -> list[BorradorDTO]:
    """Lista borradores del expediente: propios (cualquier estado) + publicados de otros.

    Regla 7: el propietario ve todo lo suyo; los publicados los ve cualquiera
    (supervisor/operador via require_consulta_user, admin bloqueado).
    """
    borradores = await listar_uc.ejecutar(expediente_id=expediente_id, usuario_id=current_user.id)

    # Resolver autor (nombre + cargo) por propietario con cache (puede haber
    # borradores publicados de otros usuarios).
    cache: dict[int, tuple[str | None, str | None]] = {}
    dto: list[BorradorDTO] = []
    for b in borradores:
        if b.propietario_id not in cache:
            cache[b.propietario_id] = await _autor_de(b.propietario_id, auth_repo)
        nombre, cargo = cache[b.propietario_id]
        dto.append(_to_dto(b, autor_nombre=nombre, autor_cargo=cargo))
    return dto


@router.get(
    "/{borrador_id}",
    response_model=BorradorDTO,
    status_code=status.HTTP_200_OK,
    summary="Obtener un borrador",
)
async def obtener_borrador(
    borrador_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("borradores", "leer"))],
    obtener_uc: ObtenerBorradorDep,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
) -> BorradorDTO:
    """Obtiene un borrador por id (Regla 7: borradores 'borrador' solo para el propietario).

    Raises:
        403: BorradorNoPropioError (no es propietario y esta en borrador).
        404: ValueError (borrador no existe).
    """
    try:
        borrador = await obtener_uc.ejecutar(borrador_id=borrador_id, usuario_id=current_user.id)
    except BorradorNoPropioError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    nombre, cargo = await _autor_de(borrador.propietario_id, auth_repo)
    return _to_dto(borrador, autor_nombre=nombre, autor_cargo=cargo)


class ContextoExportDTO(BaseModel):
    """Config de pagina/fuente para la preview (mismo que export .docx)."""

    tamano_hoja: str
    margenes: dict
    font: str
    size_pt: float


@router.get(
    "/{borrador_id}/contexto-export",
    response_model=ContextoExportDTO,
    status_code=status.HTTP_200_OK,
    summary="Contexto de export para la preview fiel (tamano/margenes/fuente)",
)
async def contexto_export_borrador(
    borrador_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("borradores", "leer"))],
    obtener_uc: ObtenerBorradorDep,
    formato_repo: FormatoRepoDep,
) -> ContextoExportDTO:
    """Devuelve tamano_hoja/margenes/font usados por el export .docx.

    El frontend lo usa para sembrar la preview identica al export (WYSIWYG).
    """
    try:
        borrador = await obtener_uc.ejecutar(borrador_id=borrador_id, usuario_id=current_user.id)
    except BorradorNoPropioError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    formato = None
    try:
        from src.application.borradores.exportar_borrador import (
            TIPO_BORRADOR_A_FORMATO,
        )

        tipo_formato = TIPO_BORRADOR_A_FORMATO.get(borrador.tipo)
        if tipo_formato:
            items, _ = await formato_repo.listar(
                tipo_documento=tipo_formato, estado="canonico", pagina=1, por_pagina=1
            )
            if items:
                formato = items[0]
            else:
                items2, _ = await formato_repo.listar(
                    tipo_documento=tipo_formato, pagina=1, por_pagina=10
                )
                if items2:
                    formato = next((f for f in items2 if f.autor == "aliaga"), items2[0])
    except Exception:
        formato = None

    from src.application.borradores.exportar_borrador import resolver_contexto_export

    ctx = resolver_contexto_export(formato)
    return ContextoExportDTO(**ctx)


@router.get(
    "/{borrador_id}/export",
    status_code=status.HTTP_200_OK,
    summary="Exportar borrador a Word (.docx)",
)
async def exportar_borrador_docx(
    borrador_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("borradores", "leer"))],
    obtener_uc: ObtenerBorradorDep,
    formato_repo: FormatoRepoDep,
) -> StreamingResponse:
    """Devuelve el borrador como archivo .docx (Regla 7: publicado visible a cualquiera).

    El contenido markdown se convierte a parrafos de Word listos para
    que el usuario ponga formato. Requiere `python-docx`.

    Raises:
        403: BorradorNoPropioError (no es propietario y esta en borrador).
        404: ValueError (borrador no existe).
    """
    try:
        borrador = await obtener_uc.ejecutar(borrador_id=borrador_id, usuario_id=current_user.id)
    except BorradorNoPropioError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    # Fusion con formato canonico si existe (tamaño hoja + estilo del esqueleto)
    formato = None
    try:
        from src.application.borradores.exportar_borrador import (
            TIPO_BORRADOR_A_FORMATO,
        )

        tipo_formato = TIPO_BORRADOR_A_FORMATO.get(borrador.tipo)
        if tipo_formato:
            items, _ = await formato_repo.listar(
                tipo_documento=tipo_formato, estado="canonico", pagina=1, por_pagina=1
            )
            if items:
                formato = items[0]
            else:
                items2, _ = await formato_repo.listar(
                    tipo_documento=tipo_formato, pagina=1, por_pagina=10
                )
                if items2:
                    formato = next((f for f in items2 if f.autor == "aliaga"), items2[0])
    except Exception:
        formato = None

    contenido_docx = generar_docx(borrador, formato)  # type: ignore[arg-type]

    filename = f"borrador_{borrador.id}_{borrador.tipo}.docx"
    return StreamingResponse(
        io.BytesIO(contenido_docx),
        media_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/{borrador_id}/solicitar-oficial",
    response_model=BorradorDTO,
    summary="Solicitar que un obrado pase a oficial (operador, propietario)",
)
async def solicitar_oficial(
    borrador_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("borradores", "actualizar"))],
    borrador_repo: BorradorRepoDep,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    audit_repo: AuditLogRepoDep,
) -> BorradorDTO:
    """Operador propietario: 'publicado' -> 'pendiente_oficial'.

    El obrado queda en revisión del supervisor (que lo aprueba o lo devuelve).
    Regla 7: solo el propietario puede solicitar.
    """
    actualizado = await borrador_repo.actualizar_estado(
        borrador_id, "pendiente_oficial", propietario_id=current_user.id
    )
    if actualizado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Obrado no encontrado, no es de tu propiedad o no está publicado.",
        )
    await registrar_auditoria_segura(
        audit_repo,
        accion="solicitar_oficial",
        usuario_id=current_user.id,
        entidad="borrador",
        entidad_id=borrador_id,
    )
    nombre, cargo = await _autor_de(current_user.id, auth_repo)
    return _to_dto(actualizado, autor_nombre=nombre, autor_cargo=cargo)


@router.post(
    "/{borrador_id}/aprobar-oficial",
    response_model=BorradorDTO,
    summary="Aprobar un obrado como oficial (supervisor)",
)
async def aprobar_oficial(
    borrador_id: int,
    current_user: Annotated[Usuario, Depends(require_supervisor)],
    borrador_repo: BorradorRepoDep,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    expediente_repo: ExpedienteRepoDep,
    obra_repo: ObraRepoDep,
    fragmento_repo: FragmentoRepoDep,
    vector_repo: VectorRepoDep,
    embedder: EmbedderDep,
    audit_repo: AuditLogRepoDep,
) -> BorradorDTO:
    """Supervisor: 'pendiente_oficial' -> 'oficial' y crea obra indexada visible a todos."""
    actualizado = await borrador_repo.actualizar_estado_supervisor(
        borrador_id, "oficial", desde="pendiente_oficial"
    )
    if actualizado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Obrado no encontrado o no pendiente de oficial.",
        )
    await registrar_auditoria_segura(
        audit_repo,
        accion="aprobar_oficial",
        usuario_id=current_user.id,
        entidad="borrador",
        entidad_id=borrador_id,
    )
    # Oficializar -> crear obra institucional (publicada, autor=tribunal, indexada).
    # Opcion 1: propietario es tribunal (visible a todos), todos indexan.
    try:
        from src.application.expedientes.indexar_obra import IndexarObra
        from src.domain.entities.obra import Obra

        expediente = await expediente_repo.obtener(actualizado.expediente_id)
        tribunal = expediente.tribunal_origen if expediente else None
        # Mapeo borrador tipo -> obra tipo_documento
        tipo_map = {
            "dictamen_radicatoria": "dictamen_radicatoria",
            "proyecto_auto_vista_consulta": "auto_vista",
            "proyecto_auto_vista_apelacion": "auto_vista",
            "sugerencia_argumentacion": "otro",
        }
        tipo_obra = tipo_map.get(actualizado.tipo, "otro")
        obra = Obra(
            id=None,
            expediente_id=actualizado.expediente_id,
            propietario_id=actualizado.propietario_id,
            tipo_documento=tipo_obra,  # type: ignore[arg-type]
            nombre_archivo=f"borrador_{actualizado.id}_{actualizado.tipo}.txt",
            contenido_texto=actualizado.contenido or "",
            estado_visibilidad="publicado",
            fuente="generado_sistema",
            estado_procesamiento="pendiente",
            autor_instancia=tribunal,
        )
        guardada = await obra_repo.guardar(obra)
        # Indexar best-effort: si falla, obra queda pendiente (no bloquea oficializacion)
        try:
            await IndexarObra(
                obra_repo=obra_repo,
                fragmento_repo=fragmento_repo,
                embedder=embedder,
                vector_repo=vector_repo,
            ).ejecutar(guardada)
        except Exception:
            log.exception("Fallo al indexar la obra oficial (obra_id=%s)", guardada.id)
        # N4 (niveles-corpus): el Auto/Dictamen oficial se vuelve ejemplo
        # global del TSJM (ilustrativo, no vinculante). Idempotente: si el
        # supervisor re-aprueba, no se duplica.
        nombre_ejemplo = f"ejemplo_borrador_{actualizado.id}_{actualizado.tipo}.txt"
        if not await obra_repo.existe_obra(actualizado.expediente_id, "ejemplo", nombre_ejemplo):
            ejemplo = Obra(
                id=None,
                expediente_id=actualizado.expediente_id,
                propietario_id=actualizado.propietario_id,
                tipo_documento="ejemplo",  # type: ignore[arg-type]
                nombre_archivo=nombre_ejemplo,
                contenido_texto=actualizado.contenido or "",
                estado_visibilidad="global",
                fuente="generado_sistema",
                estado_procesamiento="pendiente",
                autor_instancia=tribunal,
            )
            guardada_ejemplo = await obra_repo.guardar(ejemplo)
            try:
                await IndexarObra(
                    obra_repo=obra_repo,
                    fragmento_repo=fragmento_repo,
                    embedder=embedder,
                    vector_repo=vector_repo,
                ).ejecutar(guardada_ejemplo)
            except Exception:
                log.exception(
                    "Fallo al indexar el ejemplo global (obra_id=%s)", guardada_ejemplo.id
                )
    except Exception:
        # No bloquear oficializacion por error de indexado/obrado
        log.exception("Fallo al crear las obras de la oficializacion (borrador_id=%s)", borrador_id)
    # Para obrados oficiales, el autor visible es el tribunal, no el usuario
    if actualizado.estado == "oficial":
        try:
            expediente = await expediente_repo.obtener(actualizado.expediente_id)
            tribunal = expediente.tribunal_origen if expediente else None
            if tribunal:
                return _to_dto(actualizado, autor_nombre=tribunal, autor_cargo=None)
        except Exception:
            log.warning(
                "No se pudo resolver el tribunal (borrador_id=%s)", borrador_id, exc_info=True
            )
    nombre, cargo = await _autor_de(actualizado.propietario_id, auth_repo)
    return _to_dto(actualizado, autor_nombre=nombre, autor_cargo=cargo)


@router.post(
    "/{borrador_id}/desoficializar",
    response_model=BorradorDTO,
    summary="Desoficializar un obrado (supervisor, por error)",
)
async def desoficializar(
    borrador_id: int,
    current_user: Annotated[Usuario, Depends(require_supervisor)],
    body: DesoficializarBody,
    borrador_repo: BorradorRepoDep,
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    obra_repo: ObraRepoDep,
    audit_repo: AuditLogRepoDep,
) -> BorradorDTO:
    """Supervisor: 'oficial' -> 'pendiente_oficial' | 'publicado' | 'borrador'.

    'pendiente_oficial' es el camino para corregir un oficial (vuelve a la solicitud,
    se corrige y se oficializa de nuevo). Solo aplica a un borrador oficial.

    Archiva el ejemplo N4 creado al oficializar (best-effort): ya no
    refleja lo oficializado.
    """
    actualizado = await borrador_repo.actualizar_estado_supervisor(
        borrador_id, body.destino, desde="oficial"
    )
    if actualizado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Obrado no encontrado o no esta oficial.",
        )
    with contextlib.suppress(Exception):
        await obra_repo.archivar_ejemplos_borrador(actualizado.expediente_id, borrador_id)
    await registrar_auditoria_segura(
        audit_repo,
        accion="desoficializar",
        usuario_id=current_user.id,
        entidad="borrador",
        entidad_id=borrador_id,
        detalle={"destino": body.destino},
    )
    nombre, cargo = await _autor_de(actualizado.propietario_id, auth_repo)
    return _to_dto(actualizado, autor_nombre=nombre, autor_cargo=cargo)


__all__ = ["router"]
