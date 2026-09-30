"""Router /fuentes — flujo común de normas, jurisprudencia y doctrina (libros).

Las tres categorías se guardan en `norma` y comparten el flujo privada ->
pendiente -> global: el operador sube y propone, el supervisor aprueba (o rechaza
con motivo) y puede cargar directo a global. Sustituye a los endpoints dispersos de
`/doctrina` (que quedan como alias de lectura) para la UI nueva.
"""

from __future__ import annotations

import contextlib
import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from src.adapters.http.dependencies import (
    AuditLogRepoDep,
    EmbedderDep,
    FragmentoRepoDep,
    NormaRepoDep,
    ObraRepoDep,
    TextExtractorDep,
    ValidadorDep,
    VectorRepoDep,
    VectorRepoDoctrinaDep,
    VectorRepoJurisprudenciaDep,
    require_permiso,
    require_supervisor,
)
from src.adapters.http.upload import leer_upload
from src.application.admin.audit import registrar_auditoria
from src.application.corpus.indexar_norma import IndexarNorma
from src.application.doctrina.seleccionar_corpus import (
    CorpusNoSeleccionableError,
    SeleccionarCorpus,
    SeleccionarCorpusRequest,
)
from src.application.fuentes.casos_de_uso import (
    FuenteNoEncontradaError,
    FuenteNoPropiaError,
    FuenteResumen,
    ListarFuentes,
    PromoverObraANorma,
    ProponerFuente,
    ResolverFuente,
    SubirFuente,
    TransicionInvalidaError,
)
from src.application.services.trabajos_indexado import TokenCancelacion, registro
from src.config import get_settings
from src.domain.entities.usuario import Usuario
from src.domain.services.validador_upload import UploadInvalidoError
from src.routers.trabajos import TrabajoEncoladoResp

router = APIRouter(prefix="/fuentes", tags=["fuentes"])

Categoria = Literal["norma", "jurisprudencia", "doctrina"]
_ROLES_DIRECTOS = ("supervisor", "administrador")


class FuenteDTO(BaseModel):
    id: int
    abreviatura: str
    nombre: str
    categoria: str
    subgrupo: str | None
    estado_visibilidad: str
    propietario_id: int | None
    es_propia: bool
    motivo_rechazo: str | None


class ResolverBody(BaseModel):
    aprobar: bool
    motivo: str | None = Field(default=None, max_length=500)


class DesdeObraBody(BaseModel):
    nombre: str = Field(min_length=3, max_length=200)
    jerarquia: Literal["suprema", "militar", "supletoria"]


class ResolucionTribunalDTO(BaseModel):
    obra_id: int
    nombre_archivo: str
    tipo_documento: str
    expediente_id: int | None


class SeleccionarBody(BaseModel):
    expediente_id: int | None = None


class PunteroResp(BaseModel):
    obra_id: int
    estado_visibilidad: str


def _dto(f: FuenteResumen) -> FuenteDTO:
    return FuenteDTO(**{k: getattr(f, k) for k in FuenteDTO.model_fields})


def _vectores(norma, jurisprudencia, doctrina) -> dict:
    return {"norma": norma, "jurisprudencia": jurisprudencia, "doctrina": doctrina}


@router.get("", response_model=list[FuenteDTO], summary="Fuentes de una categoría")
async def get_fuentes(
    categoria: Annotated[Categoria, Query()],
    current_user: Annotated[Usuario, Depends(require_permiso("doctrina", "leer"))],
    norma_repo: NormaRepoDep,
) -> list[FuenteDTO]:
    """Lo global, lo propio y —para el supervisor— lo pendiente de aprobación."""
    fuentes = await ListarFuentes(norma_repo).ejecutar(
        categoria,
        usuario_id=current_user.id,  # type: ignore[arg-type]
        es_supervisor=current_user.rol in _ROLES_DIRECTOS,
    )
    return [_dto(f) for f in fuentes]


@router.get("/pendientes", response_model=list[FuenteDTO], summary="Cola de aprobación")
async def get_pendientes(
    current_user: Annotated[Usuario, Depends(require_supervisor)],
    norma_repo: NormaRepoDep,
) -> list[FuenteDTO]:
    fuentes = await ListarFuentes(norma_repo).pendientes(usuario_id=current_user.id)  # type: ignore[arg-type]
    return [_dto(f) for f in fuentes]


@router.get(
    "/resoluciones-tribunal",
    response_model=list[ResolucionTribunalDTO],
    summary="Resoluciones del tribunal: obrados promovidos y autos oficializados",
)
async def get_resoluciones_tribunal(
    _user: Annotated[Usuario, Depends(require_permiso("doctrina", "leer"))],
    obra_repo: ObraRepoDep,
) -> list[ResolucionTribunalDTO]:
    """Jurisprudencia del propio tribunal (subgrupo de jurisprudencia junto a TCP y CIDH)."""
    return [
        ResolucionTribunalDTO(
            obra_id=o.id,
            nombre_archivo=o.nombre_archivo,
            tipo_documento=o.tipo_documento,
            expediente_id=o.expediente_id,
        )
        for o in await obra_repo.listar_por_estado("global")
        if o.tipo_documento in ("jurisprudencia", "ejemplo")
    ]


@router.post(
    "",
    response_model=TrabajoEncoladoResp,
    status_code=202,
    summary="Encolar la indexacion de una fuente subida",
)
async def post_fuente(
    current_user: Annotated[Usuario, Depends(require_permiso("doctrina", "crear"))],
    file: UploadFile,
    norma_repo: NormaRepoDep,
    fragmento_repo: FragmentoRepoDep,
    vector_repo: VectorRepoDep,
    vector_repo_jurisprudencia: VectorRepoJurisprudenciaDep,
    vector_repo_doctrina: VectorRepoDoctrinaDep,
    embedder: EmbedderDep,
    text_extractor: TextExtractorDep,
    validador: ValidadorDep,
    audit_repo: AuditLogRepoDep,
    categoria: Annotated[Categoria, Form()],
    nombre: Annotated[str, Form(min_length=3, max_length=200)],
    tipo: Annotated[str | None, Form()] = None,
    jerarquia: Annotated[str | None, Form()] = None,
) -> TrabajoEncoladoResp:
    """El operador sube privado; el supervisor, directo a global.

    La indexacion se encola: responde 202 con el id del trabajo, que se
    sigue en /jobs/{job_id} y se puede cancelar ahi.
    """
    data = await leer_upload(file)
    try:
        validador.validar(
            file.filename or "documento", file.content_type or "application/octet-stream", data
        )
    except UploadInvalidoError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None

    upload_dir = Path(get_settings().upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = upload_dir / f"{uuid.uuid4()}.tmp"
    tmp_path.write_bytes(data)
    indexar = IndexarNorma(
        text_extractor=text_extractor,
        embedder=embedder,
        vector_repo=vector_repo,
        norma_repo=norma_repo,
        fragmento_repo=fragmento_repo,
        vector_repo_jurisprudencia=vector_repo_jurisprudencia,
        vector_repo_doctrina=vector_repo_doctrina,
    )
    subir = SubirFuente(indexar, norma_repo)

    async def _indexar(token: TokenCancelacion):
        """Indexa la fuente; el temporal y la auditoria son del trabajo."""
        try:
            resultado = await subir.ejecutar(
                categoria=categoria,
                nombre=nombre,
                ruta=tmp_path,
                usuario_id=current_user.id,  # type: ignore[arg-type]
                es_supervisor=current_user.rol in _ROLES_DIRECTOS,
                tipo=tipo,
                jerarquia=jerarquia,
                token=token,
            )
        finally:
            # El temporal vive lo que vive el trabajo, no la request.
            tmp_path.unlink(missing_ok=True)

        norma = await norma_repo.get_by_id(resultado.norma_id)
        with contextlib.suppress(Exception):
            await registrar_auditoria(
                audit_repo,
                accion="subir_fuente",
                usuario_id=current_user.id,
                entidad="norma",
                entidad_id=resultado.norma_id,
                detalle={"categoria": categoria, "abreviatura": norma.abreviatura},
            )
        return resultado

    job = registro.lanzar(
        tipo="fuente",
        usuario_id=current_user.id,
        fabrica=_indexar,  # type: ignore[arg-type]
    )
    return TrabajoEncoladoResp(job_id=job.id, estado=job.estado.value)


@router.post(
    "/desde-obra/{obra_id}",
    response_model=TrabajoEncoladoResp,
    status_code=202,
    summary="Promover un obrado publicado a norma del corpus",
)
async def post_desde_obra(
    obra_id: int,
    body: DesdeObraBody,
    current_user: Annotated[Usuario, Depends(require_permiso("obras", "actualizar"))],
    norma_repo: NormaRepoDep,
    obra_repo: ObraRepoDep,
    fragmento_repo: FragmentoRepoDep,
    vector_repo: VectorRepoDep,
    vector_repo_jurisprudencia: VectorRepoJurisprudenciaDep,
    vector_repo_doctrina: VectorRepoDoctrinaDep,
    embedder: EmbedderDep,
    text_extractor: TextExtractorDep,
    audit_repo: AuditLogRepoDep,
) -> TrabajoEncoladoResp:
    """El operador propone (queda pendiente); el supervisor promueve directo a global.

    Los checks (obra existe, es propia, esta publicada, no promovida ya) son
    sincronicos y responden 404/403/409/422 de inmediato. Pasada la validacion,
    el indexado (lento) se encola: 202 con el job_id, que se sigue en
    /jobs/{job_id} y se puede cancelar ahi.
    """
    es_supervisor = current_user.rol in _ROLES_DIRECTOS
    indexar = IndexarNorma(
        text_extractor=text_extractor,
        embedder=embedder,
        vector_repo=vector_repo,
        norma_repo=norma_repo,
        fragmento_repo=fragmento_repo,
        vector_repo_jurisprudencia=vector_repo_jurisprudencia,
        vector_repo_doctrina=vector_repo_doctrina,
    )
    promotor = PromoverObraANorma(indexar, norma_repo, obra_repo)
    try:
        obra = await promotor.validar(
            obra_id=obra_id,
            usuario_id=current_user.id,  # type: ignore[arg-type]
            es_supervisor=es_supervisor,
        )
    except FuenteNoEncontradaError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FuenteNoPropiaError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TransicionInvalidaError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    async def _indexar(token: TokenCancelacion):
        """Indexa el obrado ya validado; la auditoria es del trabajo."""
        resultado = await promotor.indexar(
            obra,
            obra_id=obra_id,
            usuario_id=current_user.id,  # type: ignore[arg-type]
            es_supervisor=es_supervisor,
            nombre=body.nombre,
            jerarquia=body.jerarquia,
            token=token,
        )
        with contextlib.suppress(Exception):
            await registrar_auditoria(
                audit_repo,
                accion="promover_obra_a_norma",
                usuario_id=current_user.id,
                entidad="obra",
                entidad_id=obra_id,
                detalle={"norma_id": resultado.norma_id},
            )
        return resultado

    job = registro.lanzar(
        tipo="obra_a_norma",
        usuario_id=current_user.id,  # type: ignore[arg-type]
        fabrica=_indexar,  # type: ignore[arg-type]
    )
    return TrabajoEncoladoResp(job_id=job.id, estado=job.estado.value)


@router.post("/{fuente_id}/proponer", response_model=FuenteDTO, summary="Proponer a global")
async def post_proponer(
    fuente_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("doctrina", "actualizar"))],
    norma_repo: NormaRepoDep,
    vector_repo: VectorRepoDep,
    vector_repo_jurisprudencia: VectorRepoJurisprudenciaDep,
    vector_repo_doctrina: VectorRepoDoctrinaDep,
    audit_repo: AuditLogRepoDep,
) -> FuenteDTO:
    uc = ProponerFuente(
        norma_repo, _vectores(vector_repo, vector_repo_jurisprudencia, vector_repo_doctrina)
    )
    try:
        fuente = await uc.ejecutar(fuente_id=fuente_id, usuario_id=current_user.id)  # type: ignore[arg-type]
    except FuenteNoEncontradaError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FuenteNoPropiaError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TransicionInvalidaError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="proponer_fuente",
            usuario_id=current_user.id,
            entidad="norma",
            entidad_id=fuente_id,
        )
    return _dto(fuente)


@router.post("/{fuente_id}/resolver", response_model=FuenteDTO, summary="Aprobar o rechazar")
async def post_resolver(
    fuente_id: int,
    body: ResolverBody,
    current_user: Annotated[Usuario, Depends(require_supervisor)],
    norma_repo: NormaRepoDep,
    vector_repo: VectorRepoDep,
    vector_repo_jurisprudencia: VectorRepoJurisprudenciaDep,
    vector_repo_doctrina: VectorRepoDoctrinaDep,
    audit_repo: AuditLogRepoDep,
) -> FuenteDTO:
    uc = ResolverFuente(
        norma_repo, _vectores(vector_repo, vector_repo_jurisprudencia, vector_repo_doctrina)
    )
    try:
        fuente = await uc.ejecutar(fuente_id=fuente_id, aprobar=body.aprobar, motivo=body.motivo)
    except FuenteNoEncontradaError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TransicionInvalidaError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="aprobar_fuente" if body.aprobar else "rechazar_fuente",
            usuario_id=current_user.id,
            entidad="norma",
            entidad_id=fuente_id,
        )
    return _dto(fuente)


@router.post(
    "/{fuente_id}/seleccionar",
    response_model=PunteroResp,
    status_code=201,
    summary="Fijar la fuente al caso o a la consulta (puntero)",
)
async def post_seleccionar(
    fuente_id: int,
    body: SeleccionarBody,
    current_user: Annotated[Usuario, Depends(require_permiso("doctrina", "crear"))],
    obra_repo: ObraRepoDep,
    norma_repo: NormaRepoDep,
) -> PunteroResp:
    norma = await norma_repo.get_by_id(fuente_id)
    if norma is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Fuente id={fuente_id} no existe.")
    try:
        resp = await SeleccionarCorpus(obra_repo, norma_repo).ejecutar(
            SeleccionarCorpusRequest(
                abreviatura=norma.abreviatura,
                propietario_id=current_user.id,  # type: ignore[arg-type]
                expediente_id=body.expediente_id,
            )
        )
    except CorpusNoSeleccionableError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PunteroResp(obra_id=resp.obra_id, estado_visibilidad=resp.estado_visibilidad)
