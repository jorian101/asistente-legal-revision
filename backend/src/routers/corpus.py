"""Router admin: Gestion del Corpus Juridico (HU-04..HU-08) + Regla 3.

Sprint 2 Corpus (plan v3, F1.3). Solo admin autenticado.

Endpoints:
  GET   /admin/corpus/normas              — listar normas
  GET   /admin/corpus/normas/{norma_id}   — estado indexacion
  POST  /admin/corpus/normas              — subir PDF + indexar
  PATCH /admin/corpus/normas/{norma_id}   — editar metadatos
  DELETE /admin/corpus/normas/{norma_id}  — baja logica
  GET   /admin/corpus/fragmentos          — listar segmentos
  POST  /admin/corpus/detectar-patrones   — pre-deteccion de fuente (F1.4)
  POST  /admin/corpus/reconciliar         — reconciliar huerfanos (Regla 3)
  GET   /admin/corpus/endpoints-embedding — selector de embeddings (sin credenciales)
  GET/PUT /admin/corpus/configuracion-rag/*endpoint — selectores reranker/LLM
  GET   /admin/corpus/endpoints-llm       — selector de LLM (sin credenciales)
  GET/PATCH /admin/corpus/configuracion-rag — umbrales singleton (HU-23)
  GET/PUT /admin/corpus/configuracion-rag/normalizar-query — toggle normalizacion

Sin B008: todas las dependencias inyectadas via Depends().
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
    ConfiguracionRAGRepoDep,
    EmbedderDep,
    FragmentoRepoDep,
    NormaRepoDep,
    TextExtractorDep,
    ValidadorDep,
    VectorRepoDep,
    VectorRepoDoctrinaDep,
    VectorRepoJurisprudenciaDep,
    build_embedder,
    require_permiso,
)
from src.adapters.http.upload import leer_upload
from src.application.admin.ajustar_parametros_rag import (
    ejecutar as ejecutar_ajuste_parametros,
)
from src.application.admin.audit import registrar_auditoria
from src.application.corpus.eliminar_norma import eliminar_norma
from src.application.corpus.indexar_norma import IndexarNorma, IndexarNormaRequest
from src.application.corpus.listar_fragmentos import (
    ListarFragmentos,
    ListarFragmentosRequest,
)
from src.application.corpus.listar_normas import ListarNormas
from src.application.corpus.reconciliar_corpus import ReconciliarCorpus
from src.application.corpus.ver_estado_indexacion import VerEstadoIndexacion
from src.application.services.trabajos_indexado import TokenCancelacion, registro
from src.config import get_settings
from src.domain.entities.usuario import Usuario
from src.domain.services.segmentacion.detector_patrones import DetectorPatrones
from src.domain.services.validador_upload import UploadInvalidoError, ValidadorUpload
from src.routers.trabajos import TrabajoEncoladoResp

router = APIRouter(prefix="/admin/corpus", tags=["corpus-admin"])


# ----- DTOs ---------------------------------------------------------


class NormaResponse(BaseModel):
    norma_id: int
    abreviatura: str
    nombre: str
    tipo: str
    jerarquia: str
    version: str | None = None
    indexado: bool
    indexado_por: int | None = None


class EditarNormaRequest(BaseModel):
    nombre: str | None = None
    version: str | None = None


class EstadoResponse(BaseModel):
    norma_id: int
    abreviatura: str
    indexado: bool
    indexado_por: int | None = None
    fragmentos_count: int = 0


class ReconciliacionResponse(BaseModel):
    pg_count: int
    qdrant_count: int
    huerfanos_eliminados: int


class CandidatoPatronDTO(BaseModel):
    abreviatura: str
    articulos_matcheados: int
    confianza: float


class PatronDeteccionDTO(BaseModel):
    mejor: str | None = None
    confianza: float = 0.0
    candidatos: list[CandidatoPatronDTO] = []
    error: str | None = None


class EndpointEmbeddingResponse(BaseModel):
    id: str
    provider: str
    model: str
    dim: int


class EndpointRerankerResponse(BaseModel):
    """DTO para listar endpoints de reranker (selector UI admin).

    NO expone base_url ni api_key_env (Regla 3: credenciales viven en backend).
    """

    id: str
    provider: str
    model: str


class SeleccionRerankerRequest(BaseModel):
    """Body del PUT /admin/corpus/configuracion-rag/reranker-endpoint.

    endpoint_id vacio o null = usar el default (primer endpoint de
    RERANKER_ENDPOINTS en .env).
    """

    endpoint_id: str | None = None


class EndpointLLMResponse(BaseModel):
    """DTO para listar endpoints de LLM (selector UI admin).

    NO expone base_url ni api_key_env (Regla 3: credenciales viven en backend).
    """

    id: str
    provider: str
    model: str


class SeleccionLLMRequest(BaseModel):
    """Body del PUT /admin/corpus/configuracion-rag/llm-endpoint.

    endpoint_id vacio o null = usar el default (primer endpoint de
    LLM_ENDPOINTS en .env).
    """

    endpoint_id: str | None = None


class NormalizarQueryResponse(BaseModel):
    """Respuesta del toggle de normalizacion de query (Capa A, bug sala)."""

    activado: bool


class NormalizarQueryRequest(BaseModel):
    """Body del PUT /admin/corpus/configuracion-rag/normalizar-query."""

    activado: bool


class ConfiguracionRAGResponse(BaseModel):
    """Estado completo de la configuracion singleton (HU-23).

    Incluye los umbrales ajustables en runtime y los modelos activos
    (solo lectura: los endpoints se cambian via PUTs dedicados).
    """

    score_threshold: float
    top_k_denso: int
    top_k_lexico: int
    top_k_final: int
    max_profundidad_bfs: int
    top_k_padres_a_incluir: int
    temperatura: float
    modelo_embeddings: str
    modelo_llm_default: str
    normalizar_query: bool
    reranker_endpoint_id: str | None = None
    llm_endpoint_id: str | None = None
    actualizado_por: int | None = None
    updated_at: str | None = None


class AjusteParametrosRequest(BaseModel):
    """Body del PATCH /admin/corpus/configuracion-rag (HU-23).

    Todos los campos opcionales: PATCH parcial. La validacion de rangos
    autoritativa vive en el dominio; los constraints de Pydantic solo
    dan errores 422 tempranos.
    """

    score_threshold: float | None = Field(default=None, ge=0, le=1)
    top_k_denso: int | None = Field(default=None, ge=1, le=200)
    top_k_lexico: int | None = Field(default=None, ge=1, le=200)
    top_k_final: int | None = Field(default=None, ge=1, le=100)
    max_profundidad_bfs: int | None = Field(default=None, ge=1, le=10)
    top_k_padres_a_incluir: int | None = Field(default=None, ge=0, le=50)
    temperatura: float | None = Field(default=None, ge=0, le=1.5)


class FragmentoResponse(BaseModel):
    id: int
    norma_id: int | None = None
    qdrant_point_id: str
    texto: str
    padre_ref_key: str | None = None
    nivel_jerarquico: int | None = None
    tipo_chunk: str | None = None


class PaginaFragmentosResponse(BaseModel):
    items: list[FragmentoResponse]
    total: int
    pagina: int
    por_pagina: int


# ----- Endpoints ----------------------------------------------------


@router.get("/endpoints-embedding", response_model=list[EndpointEmbeddingResponse])
async def listar_endpoints_embedding(
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "leer"))],
):
    """Sprint 2: lista los endpoints de embeddings disponibles (selector UI).

    Devuelve solo {id, provider, model, dim}. NO expone base_url ni
    api_key_env (Trail of Bits Regla 3: las credenciales viven solo en backend).
    """
    settings = get_settings()
    return [
        EndpointEmbeddingResponse(
            id=ep["id"],
            provider=ep["provider"],
            model=ep["model"],
            dim=ep["dim"],
        )
        for ep in settings.embedding_endpoints
    ]


@router.get("/endpoints-reranker", response_model=list[EndpointRerankerResponse])
async def listar_endpoints_reranker(
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "leer"))],
):
    """Sprint 3: lista los endpoints de reranker disponibles (selector UI admin).

    Devuelve solo {id, provider, model}. NO expone base_url ni api_key_env
    (Trail of Bits Regla 3: las credenciales viven solo en backend).
    El admin selecciona el activo via
    PUT /admin/corpus/configuracion-rag/reranker-endpoint.
    """
    settings = get_settings()
    return [
        EndpointRerankerResponse(
            id=ep["id"],
            provider=ep["provider"],
            model=ep["model"],
        )
        for ep in settings.reranker_endpoints
    ]


@router.get("/fragmentos", response_model=PaginaFragmentosResponse)
async def listar_fragmentos(
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "leer"))],
    fragmento_repo: FragmentoRepoDep,
    pagina: int = 1,
    por_pagina: int = 10,
    norma_id: int | None = None,
    tipo_chunk: str | None = None,
    nivel: int | None = None,
    texto: str | None = None,
):
    """Sprint 2: listado paginado de fragmentos/segmentos del corpus (tab UI)."""
    uc = ListarFragmentos(fragmento_repo)
    result = await uc.ejecutar(
        ListarFragmentosRequest(
            pagina=pagina,
            por_pagina=por_pagina,
            norma_id=norma_id,
            tipo_chunk=tipo_chunk,
            nivel_jerarquico=nivel,
            texto=texto,
        )
    )
    return PaginaFragmentosResponse(
        items=[
            FragmentoResponse(
                id=f.id,
                norma_id=f.norma_id,
                qdrant_point_id=f.qdrant_point_id,
                texto=f.texto,
                padre_ref_key=f.padre_ref_key,
                nivel_jerarquico=f.nivel_jerarquico,
                tipo_chunk=f.tipo_chunk,
            )
            for f in result.items
        ],
        total=result.total,
        pagina=result.pagina,
        por_pagina=result.por_pagina,
    )


@router.get("/normas", response_model=list[NormaResponse])
async def listar_normas(
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "leer"))],
    norma_repo: NormaRepoDep,
    orden: Annotated[
        Literal["abreviatura", "nombre", "tipo", "jerarquia", "indexado"],
        Query(description="Campo de ordenamiento del listado (TI-01)."),
    ] = "abreviatura",
):
    """HU-04: lista todas las normas del corpus juridico, ordenadas (TI-01)."""
    uc = ListarNormas(norma_repo)
    normas = await uc.ejecutar(orden=orden)
    return [
        NormaResponse(
            norma_id=n.norma_id,
            abreviatura=n.abreviatura,
            nombre=n.nombre,
            tipo=n.tipo,
            jerarquia=n.jerarquia,
            version=n.version,
            indexado=n.indexado,
            indexado_por=n.indexado_por,
        )
        for n in normas
    ]


@router.get("/normas/{norma_id}", response_model=EstadoResponse)
async def ver_estado(
    norma_id: int,
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "leer"))],
    norma_repo: NormaRepoDep,
    fragmento_repo: FragmentoRepoDep,
):
    """HU-04: estado de indexacion de una norma especifica."""
    uc = VerEstadoIndexacion(norma_repo, fragmento_repo)
    estado = await uc.ejecutar(norma_id)
    if estado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return EstadoResponse(
        norma_id=estado.norma_id,
        abreviatura=estado.abreviatura,
        indexado=estado.indexado,
        indexado_por=estado.indexado_por,
        fragmentos_count=estado.fragmentos_count,
    )


@router.delete(
    "/normas/{norma_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar norma del corpus (soft delete)",
)
async def delete_norma(
    norma_id: int,
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "eliminar"))],
    norma_repo: NormaRepoDep,
    audit_repo: AuditLogRepoDep,
) -> None:
    """Soft delete de una norma (CRITICAL #3): activo=False.

    Conserva los fragmentos indexados para auditoria (no borrado fisico).
    Registra la accion en audit_log (Trail of Bits R6).

    Raises:
        404: norma inexistente o ya inactiva.
    """
    eliminado = await eliminar_norma(norma_repo, norma_id=norma_id)
    if not eliminado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Norma no encontrada.",
        )

    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="eliminar_norma",
            usuario_id=_admin.id,
            entidad="norma",
            entidad_id=norma_id,
        )


@router.patch(
    "/normas/{norma_id}",
    response_model=NormaResponse,
    summary="Editar metadatos de una norma (CRUD-2)",
)
async def patch_norma(
    norma_id: int,
    body: EditarNormaRequest,
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "actualizar"))],
    norma_repo: NormaRepoDep,
    audit_repo: AuditLogRepoDep,
) -> NormaResponse:
    """Modifica nombre y/o versión de una norma. Solo admin."""
    actualizado = await norma_repo.actualizar(
        norma_id,
        nombre=body.nombre,
        version=body.version,
    )
    if actualizado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Norma no encontrada.",
        )

    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="editar_norma",
            usuario_id=_admin.id,
            entidad="norma",
            entidad_id=norma_id,
        )

    return NormaResponse(
        norma_id=actualizado.id,  # type: ignore[arg-type]
        abreviatura=actualizado.abreviatura,
        nombre=actualizado.nombre,
        tipo=actualizado.tipo,
        jerarquia=actualizado.jerarquia,
        version=actualizado.version,
        indexado=actualizado.indexado,
        indexado_por=actualizado.indexado_por,
    )


@router.post("/normas", response_model=TrabajoEncoladoResp, status_code=202)
async def indexar_norma(
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "crear"))],
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
    abreviatura: str = Form(...),
    version: str | None = Form(None),
    endpoint_id: str | None = Form(None),
) -> TrabajoEncoladoResp:
    """HU-05/06/07: subir PDF de norma e indexar (extraer + segmentar + embed + persistir).

    La indexacion se encola: responde 202 con el id del trabajo, que se
    sigue en /jobs/{job_id} y se puede cancelar ahi.
    """
    data = await leer_upload(file)
    filename = file.filename or "documento"
    content_type = file.content_type or "application/octet-stream"

    # Regla 3: validar upload
    try:
        validador.validar(filename, content_type, data)
    except UploadInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None

    # D-S2C-03: abreviatura UNIQUE — re-subir la misma norma sin borrarla
    # antes reventaba en IntegrityError 500. 409 claro antes de procesar.
    existente = await norma_repo.get_by_abreviatura(abreviatura)
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ya existe una norma registrada con abreviatura '{abreviatura}'. "
                "Eliminala (DELETE) o edita sus metadatos (PATCH) antes de reindexar."
            ),
        )

    # Guardar PDF con UUID en disco
    safe_name = f"{uuid.uuid4()}.tmp"
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = upload_dir / safe_name
    tmp_path.write_bytes(data)

    async def _indexar(token: TokenCancelacion):
        """Indexa la norma; el temporal, el embedder ad-hoc y la auditoria son del trabajo."""
        embedder_efectivo = embedder
        try:
            # si el admin eligio un endpoint de embedding concreto, construimos
            # el embedder correspondiente; si no, usamos el default inyectado.
            if endpoint_id:
                embedder_efectivo = build_embedder(endpoint_id)
            uc = IndexarNorma(
                text_extractor=text_extractor,
                embedder=embedder_efectivo,
                vector_repo=vector_repo,
                norma_repo=norma_repo,
                fragmento_repo=fragmento_repo,
                vector_repo_jurisprudencia=vector_repo_jurisprudencia,
                vector_repo_doctrina=vector_repo_doctrina,
            )
            request = IndexarNormaRequest(
                abreviatura=abreviatura,
                ruta_pdf=tmp_path,
                version=version,
                indexado_por=_admin.id,
            )
            result = await uc.ejecutar(request, token=token)
        finally:
            if embedder_efectivo is not embedder:
                await embedder_efectivo.close()  # el default inyectado lo cierra su dependencia
            tmp_path.unlink(missing_ok=True)

        # Trail of Bits R6: la carga masiva de corpus es accion sensitiva.
        with contextlib.suppress(Exception):
            await registrar_auditoria(
                audit_repo,
                accion="indexar_norma",
                usuario_id=_admin.id,
                entidad="norma",
                entidad_id=result.norma_id,
                detalle={
                    "abreviatura": abreviatura,
                    "version": version,
                    "endpoint_id": endpoint_id,
                    "fragmentos_creados": result.fragmentos_creados,
                    "vectores_indexados": result.vectores_indexados,
                },
            )
        return result

    job = registro.lanzar(
        tipo="norma",
        usuario_id=_admin.id,
        fabrica=_indexar,  # type: ignore[arg-type]
    )
    return TrabajoEncoladoResp(job_id=job.id, estado=job.estado.value)


@router.post("/detectar-patrones", response_model=PatronDeteccionDTO)
async def detectar_patrones(
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "crear"))],
    file: UploadFile,
    text_extractor: TextExtractorDep,
):
    """F1.4: pre-deteccion de patrones de fuente. Dry-run, no persiste nada."""
    data = await leer_upload(file)
    filename = file.filename or "documento"
    content_type = file.content_type or "application/pdf"

    v = ValidadorUpload()
    try:
        v.validar(filename, content_type, data)
    except UploadInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None

    safe_name = f"detect-{uuid.uuid4()}.tmp"
    tmp_path = Path(get_settings().upload_dir) / safe_name
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.write_bytes(data)

    try:
        result = await text_extractor.extract(tmp_path)
        detector = DetectorPatrones()
        deteccion = detector.detectar(result.full_text)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    if deteccion.error:
        return PatronDeteccionDTO(error=deteccion.error)

    return PatronDeteccionDTO(
        mejor=deteccion.mejor.abreviatura if deteccion.mejor else None,
        confianza=round(deteccion.mejor.confianza, 4) if deteccion.mejor else 0.0,
        candidatos=[
            CandidatoPatronDTO(
                abreviatura=c.abreviatura,
                articulos_matcheados=c.articulos_matcheados,
                confianza=round(c.confianza, 4),
            )
            for c in deteccion.candidatos[:5]
        ],
    )


@router.post("/reconciliar", response_model=ReconciliacionResponse)
async def reconciliar(
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "crear"))],
    fragmento_repo: FragmentoRepoDep,
    vector_repo: VectorRepoDep,
    vector_repo_jurisprudencia: VectorRepoJurisprudenciaDep,
    vector_repo_doctrina: VectorRepoDoctrinaDep,
    audit_repo: AuditLogRepoDep,
):
    """Regla 3: reconciliación offline en las 3 colecciones (N1/N2/N3)."""
    uc = ReconciliarCorpus(
        fragmento_repo,
        [vector_repo, vector_repo_jurisprudencia, vector_repo_doctrina],
    )
    result = await uc.ejecutar()

    # Trail of Bits R6: borra huerfanos en Qdrant, accion sensitiva.
    with contextlib.suppress(Exception):
        await registrar_auditoria(
            audit_repo,
            accion="reconciliar_corpus",
            usuario_id=_admin.id,
            entidad="corpus",
            detalle={
                "pg_count": result.pg_count,
                "qdrant_count": result.qdrant_count,
                "huerfanos_eliminados": result.huerfanos_eliminados,
            },
        )

    return ReconciliacionResponse(
        pg_count=result.pg_count,
        qdrant_count=result.qdrant_count,
        huerfanos_eliminados=result.huerfanos_eliminados,
    )


@router.put("/configuracion-rag/reranker-endpoint", response_model=EndpointRerankerResponse)
async def seleccionar_reranker_endpoint(
    body: SeleccionRerankerRequest,
    admin: Annotated[Usuario, Depends(require_permiso("corpus", "actualizar"))],
    config_repo: ConfiguracionRAGRepoDep,
) -> EndpointRerankerResponse:
    """Selecciona el endpoint de reranker activo para el pipeline RAG (Sprint 3).

    El admin elige de la lista devuelta por GET /endpoints-reranker.
    Si endpoint_id es None o vacio, vuelve al default (primer endpoint
    de RERANKER_ENDPOINTS en .env).

    Valida que endpoint_id (si no es None) exista en RERANKER_ENDPOINTS
    para evitar guardar un ID huerfano que romperia el factory.

    Persistencia: configuracion_rag.reranker_endpoint_id (D3 singleton).
    """
    settings = get_settings()
    if body.endpoint_id is not None:
        endpoint_ids = [ep["id"] for ep in settings.reranker_endpoints]
        if not endpoint_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No hay endpoints de reranker configurados en .env.",
            )
        if body.endpoint_id not in endpoint_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Endpoint de reranker '{body.endpoint_id}' no configurado. "
                    f"Disponibles: {endpoint_ids}"
                ),
            )
        endpoint_seleccionado = next(
            ep for ep in settings.reranker_endpoints if ep["id"] == body.endpoint_id
        )
    else:
        if not settings.reranker_endpoints:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No hay endpoints de reranker configurados en .env.",
            )
        endpoint_seleccionado = settings.reranker_endpoints[0]

    await config_repo.set_reranker_endpoint_id(
        body.endpoint_id,
        actualizado_por=admin.id,
    )

    return EndpointRerankerResponse(
        id=endpoint_seleccionado["id"],
        provider=endpoint_seleccionado["provider"],
        model=endpoint_seleccionado["model"],
    )


@router.get("/configuracion-rag/reranker-endpoint", response_model=EndpointRerankerResponse)
async def obtener_reranker_endpoint_seleccionado(
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "leer"))],
    config_repo: ConfiguracionRAGRepoDep,
) -> EndpointRerankerResponse:
    """Devuelve el endpoint de reranker activo seleccionado por el admin.

    Si reranker_endpoint_id en BD es None, devuelve el default (primer
    endpoint de RERANKER_ENDPOINTS en .env). Si no hay endpoints
    configurados, devuelve 400.
    """
    settings = get_settings()
    if not settings.reranker_endpoints:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hay endpoints de reranker configurados en .env.",
        )

    cfg = await config_repo.get_config()
    selected_id = cfg.reranker_endpoint_id
    if selected_id is None:
        endpoint = settings.reranker_endpoints[0]
    else:
        endpoint = next(
            (ep for ep in settings.reranker_endpoints if ep["id"] == selected_id),
            settings.reranker_endpoints[0],
        )

    return EndpointRerankerResponse(
        id=endpoint["id"],
        provider=endpoint["provider"],
        model=endpoint["model"],
    )


@router.get("/endpoints-llm", response_model=list[EndpointLLMResponse])
async def listar_endpoints_llm(
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "leer"))],
):
    """Sprint 6: lista los endpoints de LLM disponibles (selector UI admin).

    Devuelve solo {id, provider, model}. NO expone base_url ni api_key_env
    (Trail of Bits Regla 3: las credenciales viven solo en backend).
    """
    settings = get_settings()
    return [
        EndpointLLMResponse(
            id=ep["id"],
            provider=ep["provider"],
            model=ep["model"],
        )
        for ep in settings.llm_endpoints
    ]


@router.put("/configuracion-rag/llm-endpoint", response_model=EndpointLLMResponse)
async def seleccionar_llm_endpoint(
    body: SeleccionLLMRequest,
    admin: Annotated[Usuario, Depends(require_permiso("corpus", "actualizar"))],
    config_repo: ConfiguracionRAGRepoDep,
) -> EndpointLLMResponse:
    """Selecciona el endpoint de LLM activo para generación (Sprint 6).

    Persiste en configuracion_rag.llm_endpoint_id (D3 singleton).
    """
    settings = get_settings()
    if body.endpoint_id is not None:
        endpoint_ids = [ep["id"] for ep in settings.llm_endpoints]
        if not endpoint_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No hay endpoints de LLM configurados en .env.",
            )
        if body.endpoint_id not in endpoint_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Endpoint de LLM '{body.endpoint_id}' no configurado. "
                    f"Disponibles: {endpoint_ids}"
                ),
            )
        endpoint_seleccionado = next(
            ep for ep in settings.llm_endpoints if ep["id"] == body.endpoint_id
        )
    else:
        if not settings.llm_endpoints:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No hay endpoints de LLM configurados en .env.",
            )
        endpoint_seleccionado = settings.llm_endpoints[0]

    await config_repo.set_llm_endpoint_id(
        body.endpoint_id,
        actualizado_por=admin.id,
    )

    return EndpointLLMResponse(
        id=endpoint_seleccionado["id"],
        provider=endpoint_seleccionado["provider"],
        model=endpoint_seleccionado["model"],
    )


@router.get("/configuracion-rag/llm-endpoint", response_model=EndpointLLMResponse)
async def obtener_llm_endpoint_seleccionado(
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "leer"))],
    config_repo: ConfiguracionRAGRepoDep,
) -> EndpointLLMResponse:
    """Devuelve el endpoint de LLM activo seleccionado por el admin.

    Si llm_endpoint_id en BD es None, devuelve el default (primer endpoint
    de LLM_ENDPOINTS en .env). Si no hay endpoints configurados, 400.
    """
    settings = get_settings()
    if not settings.llm_endpoints:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hay endpoints de LLM configurados en .env.",
        )

    cfg = await config_repo.get_config()
    selected_id = cfg.llm_endpoint_id
    if selected_id is None:
        endpoint = settings.llm_endpoints[0]
    else:
        endpoint = next(
            (ep for ep in settings.llm_endpoints if ep["id"] == selected_id),
            settings.llm_endpoints[0],
        )

    return EndpointLLMResponse(
        id=endpoint["id"],
        provider=endpoint["provider"],
        model=endpoint["model"],
    )


@router.put(
    "/configuracion-rag/normalizar-query",
    response_model=NormalizarQueryResponse,
)
async def set_normalizar_query(
    body: NormalizarQueryRequest,
    admin: Annotated[Usuario, Depends(require_permiso("corpus", "actualizar"))],
    config_repo: ConfiguracionRAGRepoDep,
) -> NormalizarQueryResponse:
    """Activa/desactiva la normalizacion de la query antes del embedding.

    Capa A (bug sala): saludos/muletillas/typos se limpian de la query del
    usuario para mejorar la busqueda densa (Art. 115 CPE entraba fuera del
    top-k). Desactivable por admin si prefiere la query cruda.
    """
    await config_repo.set_normalizar_query(
        body.activado,
        actualizado_por=admin.id,
    )
    return NormalizarQueryResponse(activado=body.activado)


@router.get(
    "/configuracion-rag/normalizar-query",
    response_model=NormalizarQueryResponse,
)
async def obtener_normalizar_query(
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "leer"))],
    config_repo: ConfiguracionRAGRepoDep,
) -> NormalizarQueryResponse:
    """Devuelve el estado actual del toggle de normalizacion de query."""
    cfg = await config_repo.get_config()
    return NormalizarQueryResponse(activado=cfg.normalizar_query)


# ----- Configuracion RAG: umbrales ajustables (HU-23) ----------------


def _configuracion_response(cfg) -> ConfiguracionRAGResponse:
    """Mapea la entidad de dominio al DTO de respuesta."""
    return ConfiguracionRAGResponse(
        score_threshold=cfg.score_threshold,
        top_k_denso=cfg.top_k_denso,
        top_k_lexico=cfg.top_k_lexico,
        top_k_final=cfg.top_k_final,
        max_profundidad_bfs=cfg.max_profundidad_bfs,
        top_k_padres_a_incluir=cfg.top_k_padres_a_incluir,
        temperatura=cfg.temperatura,
        modelo_embeddings=cfg.modelo_embeddings,
        modelo_llm_default=cfg.modelo_llm_default,
        normalizar_query=cfg.normalizar_query,
        reranker_endpoint_id=cfg.reranker_endpoint_id,
        llm_endpoint_id=cfg.llm_endpoint_id,
        actualizado_por=cfg.actualizado_por,
        updated_at=cfg.updated_at,
    )


@router.get("/configuracion-rag", response_model=ConfiguracionRAGResponse)
async def obtener_configuracion_rag(
    _admin: Annotated[Usuario, Depends(require_permiso("corpus", "leer"))],
    config_repo: ConfiguracionRAGRepoDep,
) -> ConfiguracionRAGResponse:
    """Devuelve la configuracion singleton completa (umbrales + modelos)."""
    cfg = await config_repo.get_config()
    return _configuracion_response(cfg)


@router.patch("/configuracion-rag", response_model=ConfiguracionRAGResponse)
async def ajustar_parametros_rag(
    body: AjusteParametrosRequest,
    admin: Annotated[Usuario, Depends(require_permiso("corpus", "actualizar"))],
    config_repo: ConfiguracionRAGRepoDep,
    audit_repo: AuditLogRepoDep,
) -> ConfiguracionRAGResponse:
    """Ajusta umbrales operativos del pipeline RAG en runtime (HU-23).

    PATCH parcial: solo los campos enviados se modifican. Valida rangos en
    el dominio y registra auditoria R6 (accion 'ajustar_configuracion_rag').
    El cambio aplica a las proximas consultas (cache invalidada).
    """
    valores = body.model_dump(exclude_none=True)
    try:
        cfg = await ejecutar_ajuste_parametros(
            repo=config_repo,
            valores=valores,
            actualizado_por=admin.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    await registrar_auditoria(
        audit_repo,
        accion="ajustar_configuracion_rag",
        usuario_id=admin.id,
        entidad="configuracion_rag",
        entidad_id=None,
        detalle=valores,
    )
    return _configuracion_response(cfg)
