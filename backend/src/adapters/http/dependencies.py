"""Dependencias FastAPI: sesion DB, usuario actual, roles.

Regla 2 Trail of Bits:
- get_current_user resuelve usuario desde JWT + BD en cada request.
- require_admin re-valida rol contra BD (no confia en claim JWT).
- AsyncSession per-request, sin estado compartido.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Annotated, cast

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.adapters.jwt_service import PyJwtService
from src.adapters.ollama.ollama_embedder import OllamaEmbedder
from src.adapters.postgres.repos.auth_repository import (
    SqlAuthRepository,
)
from src.adapters.postgres.repos.chat_repo import get_chat_repo
from src.adapters.postgres.repos.configuracion_rag_repo import (
    get_configuracion_rag_repo,
)
from src.adapters.postgres.repos.consulta_historial_repo import (
    get_consulta_historial_repo,
)
from src.adapters.postgres.repos.documento_chat_repo import get_documento_chat_repo
from src.adapters.postgres.repos.espacio_trabajo_repo import get_espacio_trabajo_repo
from src.adapters.postgres.repos.expansor_jerarquico import ExpansorJerarquicoImpl
from src.adapters.postgres.repos.expediente_repo import get_expediente_repo
from src.adapters.postgres.repos.formato_repo import get_formato_repo
from src.adapters.postgres.repos.fragmento_repo import FragmentoRepoImpl
from src.adapters.postgres.repos.mensaje_chat_repo import get_mensaje_chat_repo
from src.adapters.postgres.repos.norma_repo import SqlNormaRepo
from src.adapters.postgres.repos.obra_repo import get_obra_repo
from src.adapters.postgres.repos.recomendacion_repo import get_recomendacion_repo
from src.adapters.qdrant.qdrant_corpus_repo import QdrantCorpusRepo
from src.adapters.reranker.fallback import RerankerWithFallback
from src.adapters.reranker.http_reranker import HttpReranker
from src.adapters.salud_sistema import SaludSistemaImpl
from src.application.observability import get_event_bus
from src.application.ports.audit_log_repo import AuditLogRepo
from src.application.ports.auth_repository import AuthRepository
from src.application.ports.chat_repo import ChatRepo
from src.application.ports.configuracion_rag_repo import ConfiguracionRAGRepo
from src.application.ports.consulta_historial_repo import ConsultaHistorialRepo
from src.application.ports.corpus_vectorial import CorpusRepoVectorial
from src.application.ports.documento_chat_repo import DocumentoChatRepo
from src.application.ports.email_service import EmailService
from src.application.ports.embedder import Embedder
from src.application.ports.espacio_trabajo_repo import EspacioTrabajoRepo
from src.application.ports.expansor_contexto import ExpansorContexto
from src.application.ports.expediente_repo import ExpedienteRepo
from src.application.ports.formato_repo import FormatoRepo
from src.application.ports.fragmento_repo import FragmentoRepo
from src.application.ports.jwt_service import JwtService
from src.application.ports.mensaje_chat_repo import MensajeChatRepo
from src.application.ports.norma_repo import NormaRepo
from src.application.ports.obra_repo import ObraRepo
from src.application.ports.permiso_repo import PermisoRepo
from src.application.ports.recomendacion_repo import RecomendacionRepo
from src.application.ports.reranker import Reranker
from src.application.ports.salud_sistema import SaludSistemaRepo
from src.application.ports.text_extractor import TextExtractor, create_text_extractor
from src.application.services.hybrid_searcher import HybridSearcher
from src.application.services.pipeline_rag import PipelineRAG
from src.application.services.reranker_service import RerankerService
from src.config import get_settings
from src.domain.entities.usuario import Usuario
from src.domain.services.validador_upload import ValidadorUpload

logger = logging.getLogger(__name__)

_settings = get_settings()

_engine = create_async_engine(
    _settings.postgres_url_async,
    echo=False,
    pool_size=_settings.pg_pool_size,
    max_overflow=_settings.pg_max_overflow,
    pool_recycle=_settings.pg_pool_recycle,
    pool_pre_ping=True,
)
_AsyncSessionFactory = async_sessionmaker(_engine, expire_on_commit=False)


def get_session_factory() -> async_sessionmaker:
    """Session factory de Postgres para persistencia fuera del ciclo request.

    La usan use cases que escriben DESPUES de que FastAPI cerro la sesion del
    request (p.ej. el finally de un StreamingResponse). Devuelve un
    `async_sessionmaker` utilizable como `async with factory() as session`.
    """
    return _AsyncSessionFactory


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    async with _AsyncSessionFactory() as session:
        yield session


async def get_auth_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthRepository:
    return SqlAuthRepository(session)


async def get_jwt_service() -> JwtService:
    return PyJwtService()


async def get_email_service() -> AsyncGenerator[EmailService | None]:
    """Esta instalación no usa email: el login no pide 2FA."""
    yield None


EmailServiceDep = Annotated[EmailService | None, Depends(get_email_service)]


async def get_current_user(
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repo)],
    jwt_service: Annotated[JwtService, Depends(get_jwt_service)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Usuario:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from None

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt_service.verificar_access_token(token)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from None

    sub = payload.get("sub")
    if not sub or not sub.isdigit():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from None

    usuario = await auth_repo.get_by_id(int(sub))
    if usuario is None or not usuario.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from None

    return usuario


async def require_admin(
    current_user: Annotated[Usuario, Depends(get_current_user)],
) -> Usuario:
    if current_user.rol != "administrador":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return current_user


async def require_consulta_user(
    current_user: Annotated[Usuario, Depends(get_current_user)],
) -> Usuario:
    """Bloquea administradores del endpoint /consultas (decision D4).

    Solo supervisor y operador_juridico pueden usar el asistente.
    Admin es de gestion (usuarios + corpus), no del flujo de consulta.
    """
    if current_user.rol == "administrador":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El rol administrador no puede realizar consultas.",
        )
    if current_user.rol not in ("supervisor", "operador_juridico"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Rol {current_user.rol!r} no autorizado para /consultas. "
                "Permitidos: supervisor, operador_juridico."
            ),
        )
    return current_user


async def require_supervisor(
    current_user: Annotated[Usuario, Depends(get_current_user)],
) -> Usuario:
    """Solo supervisor puede abrir expedientes (gestion del TSJM).

    Operador juridico carga obras/consultas dentro de un expediente ya
    abierto por supervisor. Admin es de gestion (no procesal).
    """
    if current_user.rol != "supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Rol {current_user.rol!r} no autorizado. "
                "Solo 'supervisor' puede abrir expedientes."
            ),
        )
    return current_user


async def require_operador(
    current_user: Annotated[Usuario, Depends(get_current_user)],
) -> Usuario:
    """Solo operador_juridico genera/publica borradores (Sprint 6).

    Marco-practico Tabla 12: los borradores (RF-16/17/19/20/21) son trabajo
    del Operador Juridico. Supervisor supervisa expedientes y consulta, pero
    no produce borradores; admin es de gestion (no procesal).
    """
    if current_user.rol != "operador_juridico":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Rol {current_user.rol!r} no autorizado para /borradores. "
                "Solo 'operador_juridico' genera y publica borradores."
            ),
        )
    return current_user


def require_permiso(clave_modulo: str, operacion: str):
    """Factory de dependency: valida permiso CRUD efectivo sobre un módulo.

    Sistema de módulos y permisos por usuario (decision
    `plan/permisos-crud-modulos`). Re-valida contra BD en cada request
    (Regla 2 Trail of Bits: nunca confiar en el JWT ni en el frontend).

    El rol administrador siempre tiene full en los módulos de gestión
    (regla inamovible) y no accede a los módulos de consulta.

    Ejemplo de uso en un endpoint:
        @router.get("/fragmentos")
        async def listar(
            _perm: Annotated[Usuario, Depends(require_permiso("corpus", "leer"))],
            ...
        )
    """

    async def _check(
        current_user: Annotated[Usuario, Depends(get_current_user)],
        permiso_repo: PermisoRepoDep,
    ) -> Usuario:
        from src.application.permisos import resolver_permisos_usuario

        permisos = await resolver_permisos_usuario.execute(
            permiso_repo=permiso_repo,
            usuario_id=current_user.id,
            rol=current_user.rol,
        )
        efectivo = permisos.get(clave_modulo)
        if efectivo is None or not efectivo.permite(operacion):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Permiso denegado: operacion '{operacion}' sobre el modulo '{clave_modulo}'."
                ),
            )
        return current_user

    return _check


# ----- corpus / sprint 2 dependencies (sin B008) -----


def get_norma_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NormaRepo:
    return SqlNormaRepo(session)


def get_expediente_repo_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExpedienteRepo:
    return get_expediente_repo(session)


def get_obra_repo_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ObraRepo:
    return get_obra_repo(session)


def get_chat_repo_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatRepo:
    return get_chat_repo(session)


def get_mensaje_chat_repo_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MensajeChatRepo:
    return get_mensaje_chat_repo(session)


def get_espacio_trabajo_repo_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EspacioTrabajoRepo:
    return get_espacio_trabajo_repo(session)


def get_documento_chat_repo_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentoChatRepo:
    return get_documento_chat_repo(session)


def get_configuracion_rag_repo_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ConfiguracionRAGRepo:
    return get_configuracion_rag_repo(session)


def get_salud_sistema_repo_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SaludSistemaRepo:
    return SaludSistemaImpl(session)


def get_fragmento_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FragmentoRepo:
    return FragmentoRepoImpl(session)


# Los repos Qdrant son singletons de proceso: cada instancia abre un QdrantClient cuyo
# constructor hace una llamada HTTP de chequeo de version, y crear uno por request
# dejaba ese costo y un cliente sin cerrar en cada peticion (F-23). El estado que
# cachean (_sparse_checked) se renueva al reiniciar el proceso, como ya documentan.
@lru_cache(maxsize=1)
def get_vector_repo() -> CorpusRepoVectorial:
    return QdrantCorpusRepo()


@lru_cache(maxsize=1)
def get_vector_repo_jurisprudencia() -> CorpusRepoVectorial:
    """Repo de la colección `jurisprudencia` (N2: SCP + Corte IDH)."""
    from src.adapters.qdrant.qdrant_jurisprudencia_repo import (
        QdrantJurisprudenciaRepo,
    )

    return QdrantJurisprudenciaRepo()


@lru_cache(maxsize=1)
def get_vector_repo_doctrina() -> CorpusRepoVectorial:
    """Repo de la colección `doctrina` (N3: libros académicos)."""
    from src.adapters.qdrant.qdrant_doctrina_repo import QdrantDoctrinaRepo

    return QdrantDoctrinaRepo()


def cerrar_repos_vectoriales() -> None:
    """Cierra los repos Qdrant ya creados y reinicia su cache (shutdown y tests)."""
    for factoria in (get_vector_repo, get_vector_repo_jurisprudencia, get_vector_repo_doctrina):
        if factoria.cache_info().currsize:  # type: ignore[attr-defined]
            # El puerto declara close() como corrutina; el adapter Qdrant lo implementa sync.
            cast(QdrantCorpusRepo, factoria()).close()
        factoria.cache_clear()  # type: ignore[attr-defined]


async def get_embedder() -> AsyncGenerator[Embedder]:
    """Embedder por defecto del request; cierra su cliente HTTP al terminar."""
    embedder = build_embedder(None)
    try:
        yield embedder
    finally:
        await embedder.close()


def build_embedder(endpoint_id: str | None) -> Embedder:
    """Factory de embedder por endpoint (Sprint 2 multi-proveedor).

    Lee la configuracion de endpoints de embeddings (EMBEDDING_ENDPOINTS).
    Si endpoint_id es None usa el primer endpoint (default). Levanta 400 si el
    endpoint no existe. Nunca expone base_url/api_key al exterior.
    """
    settings = get_settings()
    ep = settings.embedding_endpoint(endpoint_id)
    provider = ep["provider"]
    base_url = ep["base_url"]
    # Plan C Fase 5: prefijo query/document opcional por endpoint. Si no se
    # define, el OllamaEmbedder lo deriva por modelo (bge-m3/qwen3).
    query_prefix = ep.get("query_prefix")

    if provider == "ollama":
        return OllamaEmbedder(
            base_url=base_url,
            model=ep["model"],
            dim=ep["dim"],
            query_prefix=query_prefix,
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Provider '{provider}' del endpoint '{ep['id']}' no soportado.",
    )


def get_text_extractor() -> TextExtractor:
    from src.application.ports.text_extractor import ExtractionMode

    # El límite de tamaño del extractor sigue a Settings (500 MB, Regla 3),
    # consistente con ValidadorUpload.MAX_BYTES. Sin esto regía el default
    # del adapter (50 MB) y los PDF de 51-500 MB morían en extracción.
    return create_text_extractor(
        ExtractionMode.AUTO, max_size_bytes=get_settings().max_pdf_size_bytes
    )


def get_reranker() -> Reranker | None:
    """Devuelve el reranker configurado o None si no hay endpoint.

    El boot del backend NO depende de servicios externos (LLM/reranker):
    si .env no define RERANKER_BASE_URL ni RERANKER_ENDPOINTS, retorna
    None y el pipeline degrada sin fase 3 (calidad degradada, sin
    cross-encoder). Las rutas de login/admin/dashboard siguen funcionando.

    NOTA: esta version NO lee la configuracion BD (no puede, no recibe
    config_repo). Para el flujo dinamico BP-driven usar get_reranker_dep().
    Se conserva para compatibilidad con callers que no usan FastAPI Depends
    (ej: scripts, tests unitarios).
    """
    settings = get_settings()
    if not settings.reranker_endpoints:
        return None
    try:
        return build_reranker(None)
    except RuntimeError:
        # reranker_endpoint() lanza si la lista esta vacia (race con env
        # que cambia entre el check y el build). Tratar como no-config.
        return None


def build_reranker(endpoint_id: str | None) -> Reranker:
    """Factory de reranker por endpoint (Sprint 3 multi-proveedor, decision D10).

    Lee RERANKER_ENDPOINTS. Si endpoint_id es None usa el primero (default).
    El adapter concreto habla el contrato /rerank por HTTP.

    Raises:
        RuntimeError: si no hay endpoints configurados. Los callers deben
            usar get_reranker() que ya maneja este caso devolviendo None.
    """
    settings = get_settings()
    ep = settings.reranker_endpoint(endpoint_id)
    api_key_env = ep.get("api_key_env")
    api_key = os.environ.get(api_key_env) if api_key_env else None
    if api_key_env and not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Endpoint de reranker '{ep['id']}' requiere configurar la "
            f"variable de entorno {ep['api_key_env']}.",
        )
    return HttpReranker(
        base_url=ep["base_url"],
        model=ep["model"],
        api_key=api_key,
    )


def build_reranker_with_fallback(
    selected_endpoint_id: str | None,
) -> Reranker | None:
    """Construye RerankerWithFallback con la lista de endpoints ordenada.

     El endpoint seleccionado (de la BD) va primero; los demas van despues
     en el orden declarado en RERANKER_ENDPOINTS. Si solo hay un endpoint,
     el wrapper sigue siendo util porque aísla la logica de retry de los
     adapters concretos.

     Si el endpoint seleccionado en la BD ya no existe en .env (huerfano),
    cae al default (primer endpoint) y el resto se ordena tras él.
     Si no hay endpoints configurados, retorna None (degradacion sin fase 3).
    """
    settings = get_settings()
    if not settings.reranker_endpoints:
        return None
    # Construir lista ordenada: seleccionado primero, luego el resto
    all_ids = [ep["id"] for ep in settings.reranker_endpoints]
    if selected_endpoint_id and selected_endpoint_id in all_ids:
        ordered_ids = [selected_endpoint_id] + [i for i in all_ids if i != selected_endpoint_id]
    else:
        # None o huerfano: default + resto
        ordered_ids = all_ids
    rerankers: list[Reranker] = []
    for eid in ordered_ids:
        try:
            rerankers.append(build_reranker(eid))
        except HTTPException:
            # api_key faltante: saltar este endpoint, no romper todo el boot
            logger.warning("Saltando endpoint de reranker '%s': api_key faltante", eid)
    if not rerankers:
        return None
    if len(rerankers) == 1:
        return rerankers[0]
    return RerankerWithFallback(rerankers)


async def get_reranker_dep(
    config_repo: Annotated[ConfiguracionRAGRepo, Depends(get_configuracion_rag_repo_dep)],
) -> AsyncGenerator[Reranker | None]:
    """Punto de entrada FastAPI: lee reranker_endpoint_id de la BD.

    Si la BD no tiene seleccion (None), usa el default (primer endpoint de
    RERANKER_ENDPOINTS) y construye el resto como fallback. Si no hay
    endpoints configurados, entrega None (degradacion graceful). Cierra los
    clientes HTTP del reranker al terminar el request.
    """
    settings = get_settings()
    if not settings.reranker_endpoints:
        yield None
        return
    try:
        cfg = await config_repo.get_config()
        reranker = build_reranker_with_fallback(cfg.reranker_endpoint_id)
    except RuntimeError:
        logger.warning("configuracion_rag vacia, usando default de .env")
        reranker = build_reranker_with_fallback(None)
    try:
        yield reranker
    finally:
        if reranker is not None:
            await reranker.close()


def get_validador() -> ValidadorUpload:
    return ValidadorUpload()


def get_consulta_historial_repo_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ConsultaHistorialRepo:
    return get_consulta_historial_repo(session)


def get_audit_log_repo_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuditLogRepo:
    from src.adapters.postgres.repos.audit_log_repo import get_audit_log_repo

    return get_audit_log_repo(session)


def get_permiso_repo_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PermisoRepo:
    from src.adapters.postgres.repos.permiso_repo import SqlPermisoRepo

    return SqlPermisoRepo(session)


def get_hybrid_searcher_dep(
    embedder: Annotated[Embedder, Depends(get_embedder)],
    corpus_repo: Annotated[CorpusRepoVectorial, Depends(get_vector_repo)],
    fragmento_repo: Annotated[FragmentoRepo, Depends(get_fragmento_repo)],
    config_repo: Annotated[ConfiguracionRAGRepo, Depends(get_configuracion_rag_repo_dep)],
    jurisprudencia_repo: Annotated[CorpusRepoVectorial, Depends(get_vector_repo_jurisprudencia)],
    doctrina_repo: Annotated[CorpusRepoVectorial, Depends(get_vector_repo_doctrina)],
) -> HybridSearcher:
    return HybridSearcher(
        embedder=embedder,
        corpus_repo=corpus_repo,
        fragmento_repo=fragmento_repo,
        config=config_repo,
        jurisprudencia_repo=jurisprudencia_repo,
        doctrina_repo=doctrina_repo,
    )


def get_reranker_service_dep(
    reranker: Annotated[Reranker | None, Depends(get_reranker_dep)],
) -> RerankerService:
    s = get_settings()
    return RerankerService(
        reranker=reranker,
        max_candidates=s.reranker_max_candidates,
        timeout=s.reranker_timeout_seconds,
        fallos_consecutivos=s.reranker_fallos_consecutivos,
        ventana_cooldown_s=s.reranker_cooldown_seconds,
    )


def get_expansor_contexto_dep(
    fragmento_repo: Annotated[FragmentoRepo, Depends(get_fragmento_repo)],
    obra_repo: Annotated[ObraRepo, Depends(get_obra_repo_dep)],
    config_repo: Annotated[ConfiguracionRAGRepo, Depends(get_configuracion_rag_repo_dep)],
) -> ExpansorContexto:
    """Factory del ExpansorJerarquicoImpl (Sprint 5 Fase 4)."""
    return ExpansorJerarquicoImpl(
        fragmento_repo=fragmento_repo,
        obra_repo=obra_repo,
        config_repo=config_repo,
    )


def get_pipeline_rag_dep(
    buscador: Annotated[HybridSearcher, Depends(get_hybrid_searcher_dep)],
    reranker_svc: Annotated[RerankerService, Depends(get_reranker_service_dep)],
    config_repo: Annotated[ConfiguracionRAGRepo, Depends(get_configuracion_rag_repo_dep)],
    expansor: Annotated[ExpansorContexto | None, Depends(get_expansor_contexto_dep)],
    obra_repo: ObraRepoDep,
    recomendacion_repo: RecomendacionRepoDep,
) -> PipelineRAG:
    return PipelineRAG(
        buscador=buscador,
        reranker_svc=reranker_svc,
        config_repo=config_repo,
        expansor=expansor,
        event_bus=get_event_bus(),
        obra_repo=obra_repo,
        recomendacion_repo=recomendacion_repo,
    )


NormaRepoDep = Annotated[NormaRepo, Depends(get_norma_repo)]
FragmentoRepoDep = Annotated[FragmentoRepo, Depends(get_fragmento_repo)]
VectorRepoDep = Annotated[CorpusRepoVectorial, Depends(get_vector_repo)]
VectorRepoJurisprudenciaDep = Annotated[
    CorpusRepoVectorial, Depends(get_vector_repo_jurisprudencia)
]
VectorRepoDoctrinaDep = Annotated[CorpusRepoVectorial, Depends(get_vector_repo_doctrina)]
EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
RerankerDep = Annotated[Reranker | None, Depends(get_reranker_dep)]
TextExtractorDep = Annotated[TextExtractor, Depends(get_text_extractor)]
ValidadorDep = Annotated[ValidadorUpload, Depends(get_validador)]
ConfiguracionRAGRepoDep = Annotated[ConfiguracionRAGRepo, Depends(get_configuracion_rag_repo_dep)]
ConsultaHistorialRepoDep = Annotated[
    ConsultaHistorialRepo, Depends(get_consulta_historial_repo_dep)
]
AuditLogRepoDep = Annotated[AuditLogRepo, Depends(get_audit_log_repo_dep)]
PermisoRepoDep = Annotated[PermisoRepo, Depends(get_permiso_repo_dep)]
SaludSistemaRepoDep = Annotated[SaludSistemaRepo, Depends(get_salud_sistema_repo_dep)]
HybridSearcherDep = Annotated[HybridSearcher, Depends(get_hybrid_searcher_dep)]
RerankerServiceDep = Annotated[RerankerService, Depends(get_reranker_service_dep)]
PipelineRAGDep = Annotated[PipelineRAG, Depends(get_pipeline_rag_dep)]
ExpansorContextoDep = Annotated[ExpansorContexto, Depends(get_expansor_contexto_dep)]


def get_formato_repo_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FormatoRepo:
    return get_formato_repo(session)


# Sprint 4 — Gestion de Expedientes + Chats (Opcion B fork #133)
ExpedienteRepoDep = Annotated[ExpedienteRepo, Depends(get_expediente_repo_dep)]
ObraRepoDep = Annotated[ObraRepo, Depends(get_obra_repo_dep)]
FormatoRepoDep = Annotated[FormatoRepo, Depends(get_formato_repo_dep)]


def get_recomendacion_repo_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RecomendacionRepo:
    return get_recomendacion_repo(session)


RecomendacionRepoDep = Annotated[RecomendacionRepo, Depends(get_recomendacion_repo_dep)]
ChatRepoDep = Annotated[ChatRepo, Depends(get_chat_repo_dep)]
MensajeChatRepoDep = Annotated[MensajeChatRepo, Depends(get_mensaje_chat_repo_dep)]
EspacioTrabajoRepoDep = Annotated[EspacioTrabajoRepo, Depends(get_espacio_trabajo_repo_dep)]
DocumentoChatRepoDep = Annotated[DocumentoChatRepo, Depends(get_documento_chat_repo_dep)]
