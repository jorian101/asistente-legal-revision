"""Dependencies FastAPI — Sprint 6 (Borradores).

Factories para los use cases GenerarBorrador, PublicarBorrador,
ListarBorradores y ObtenerBorrador; adapters ResolvedorPlantilla
y OllamaLLMClient; BorradorRepo.

Separado de dependencies.py para evitar megarasgo de imports y
mantener tipo-aliases limpios en un unico archivo de Sprint 6.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.http.dependencies import (
    ConfiguracionRAGRepoDep,
    ConsultaHistorialRepoDep,
    PipelineRAGDep,
    get_db_session,
)
from src.adapters.ollama.ollama_llm_client import OllamaLLMClient
from src.adapters.plantillas.plantilla_markdown_adapter import (
    PlantillaMarkdownAdapter,
)
from src.adapters.postgres.repos.borrador_repo import get_borrador_repo
from src.application.borradores.generar_borrador import GenerarBorrador
from src.application.borradores.listar_borradores import ListarBorradores
from src.application.borradores.listar_mis_borradores import ListarMisBorradores
from src.application.borradores.obtener_borrador import ObtenerBorrador
from src.application.borradores.publicar_borrador import PublicarBorrador
from src.application.observability import get_event_bus
from src.application.ports.borrador_repo import BorradorRepo
from src.application.ports.llm_client import LLMClient
from src.application.ports.resolvedor_plantilla import ResolvedorPlantilla
from src.config import get_settings

# docs/plantillas/ a nivel repo raiz (mismo path que tests Fase 2.1)
_PLANTILLAS_DIR = Path(__file__).resolve().parents[4] / "docs" / "plantillas"


# ----- BorradorRepo --------------------------------------------------


def get_borrador_repo_dep(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BorradorRepo:
    return get_borrador_repo(session)


BorradorRepoDep = Annotated[BorradorRepo, Depends(get_borrador_repo_dep)]


# ----- LLMClient ------------------------------------------------------


def build_llm(endpoint_id: str | None) -> LLMClient:
    """Factory de LLM client por endpoint (multi-proveedor, mirror build_embedder).

    Lee la configuracion de endpoints de LLM (LLM_ENDPOINTS).
    Si endpoint_id es None usa el primer endpoint (default). Levanta 400 si el
    endpoint no existe. Nunca expone base_url/api_key al exterior.
    """
    settings = get_settings()
    ep = settings.llm_endpoint(endpoint_id)
    provider = ep["provider"]
    base_url = ep["base_url"]

    # F2: presupuesto por endpoint. Si el endpoint declara context_window_tokens
    # se acota a la mitad de su ventana; si no, vale el default global.
    ventana = ep.get("context_window_tokens")
    presupuesto_default = settings.llm_presupuesto_tokens
    soporta_system = bool(ep.get("soporta_system", True))

    if provider == "ollama":
        # A.1: Ollama presupuesta contra la ventana real (num_ctx), no ventana // 2.
        return OllamaLLMClient(
            base_url=base_url,
            model=ep["model"],
            timeout=settings.ollama_timeout_seconds,
            presupuesto_tokens=presupuesto_default,
            soporta_system=soporta_system,
            **({"ventana_tokens": int(ventana)} if ventana else {}),
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Provider LLM '{provider}' del endpoint '{ep['id']}' no soportado.",
    )


def build_llm_with_fallback(selected_endpoint_id: str | None) -> LLMClient:
    """Construye LLMWithFallback con la lista ordenada de endpoints.

    El endpoint seleccionado va primero; el resto sigue en el orden declarado
    en LLM_ENDPOINTS. Si solo hay un endpoint, devuelve el cliente directo
    (sin wrapper). Si no hay endpoints, levanta 400 (no debería pasar).
    """
    from src.adapters.llm.fallback import LLMWithFallback

    settings = get_settings()
    if not settings.llm_endpoints:
        raise RuntimeError("No hay endpoints LLM configurados")
    all_ids = [ep["id"] for ep in settings.llm_endpoints]
    if selected_endpoint_id and selected_endpoint_id in all_ids:
        ordered_ids = [selected_endpoint_id] + [i for i in all_ids if i != selected_endpoint_id]
    else:
        ordered_ids = all_ids
    clients: list[LLMClient] = []
    for eid in ordered_ids:
        try:
            clients.append(build_llm(eid))
        except HTTPException:
            # api_key faltante: saltar este endpoint, no romper todo el chain
            continue
    if not clients:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ningún endpoint LLM tiene su api_key configurada.",
        )
    if len(clients) == 1:
        return clients[0]
    return LLMWithFallback(clients)


async def get_llm_client(
    config_repo: ConfiguracionRAGRepoDep,
) -> LLMClient:
    """Devuelve el LLMClient del endpoint seleccionado por admin, con fallback.

    Lee `configuracion_rag.llm_endpoint_id`; si es None usa el default
    (primer endpoint de LLM_ENDPOINTS). Si el primario falla con 503/429/5xx,
    el wrapper prueba el siguiente endpoint en orden.
    """
    cfg = await config_repo.get_config()
    return build_llm_with_fallback(cfg.llm_endpoint_id)


def llm_model_name_activo(cfg) -> str:
    """Nombre del modelo del endpoint LLM activo (para telemetría).

    `cfg.llm_endpoint_id` -> endpoint de LLM_ENDPOINTS -> campo `model`.
    Fallback al modelo legacy si no hay config o endpoint.
    """
    settings = get_settings()
    endpoint_id = cfg.llm_endpoint_id if cfg else None
    try:
        ep = settings.llm_endpoint(endpoint_id)
        return str(ep.get("model", settings.llm_model_name))
    except KeyError:
        return settings.llm_model_name


LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]


# ----- ResolvedorPlantilla -------------------------------------------


def get_resolvedor_plantilla(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResolvedorPlantilla:
    # Reusa el factory del expediente_repo (dependencies.py)
    from src.adapters.http.dependencies import get_expediente_repo_dep, get_obra_repo_dep

    return PlantillaMarkdownAdapter(
        plantillas_dir=_PLANTILLAS_DIR,
        expediente_repo=get_expediente_repo_dep(session),
        obra_repo=get_obra_repo_dep(session),
    )


ResolvedorPlantillaDep = Annotated[ResolvedorPlantilla, Depends(get_resolvedor_plantilla)]


# ----- Use cases ------------------------------------------------------


async def get_generar_borrador(
    pipeline: PipelineRAGDep,
    resolvedor: ResolvedorPlantillaDep,
    llm_client: LLMClientDep,
    borrador_repo: BorradorRepoDep,
    historial_repo: ConsultaHistorialRepoDep,
    config_repo: ConfiguracionRAGRepoDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GenerarBorrador:
    from src.adapters.http.dependencies import (
        get_expediente_repo_dep,
        get_mensaje_chat_repo_dep,
        get_obra_repo_dep,
        get_session_factory,
    )
    from src.application.services.memoria_conversacional import (
        ConstructorMemoriaConversacional,
    )

    memoria = ConstructorMemoriaConversacional(
        mensaje_repo=get_mensaje_chat_repo_dep(session),
        borrador_repo=borrador_repo,
    )

    return GenerarBorrador(
        pipeline_rag=pipeline,
        resolvedor=resolvedor,
        llm_client=llm_client,
        borrador_repo=borrador_repo,
        historial_repo=historial_repo,
        config_repo=config_repo,
        llm_model_name=llm_model_name_activo(await config_repo.get_config()),
        event_bus=get_event_bus(),
        # Fase 5 (G3/G4): repos opcionales para enriquecer la sugerencia de
        # argumentación con datos de expediente/obras (competencia real).
        expediente_repo=get_expediente_repo_dep(session),
        obra_repo=get_obra_repo_dep(session),
        memoria_conversacional=memoria,
        # F2: sesion aislada para persistir la respuesta FINAL del stream.
        session_factory=get_session_factory(),
    )


GenerarBorradorDep = Annotated[GenerarBorrador, Depends(get_generar_borrador)]


def get_publicar_borrador(borrador_repo: BorradorRepoDep) -> PublicarBorrador:
    return PublicarBorrador(borrador_repo=borrador_repo)


PublicarBorradorDep = Annotated[PublicarBorrador, Depends(get_publicar_borrador)]


def get_listar_borradores(borrador_repo: BorradorRepoDep) -> ListarBorradores:
    return ListarBorradores(borrador_repo=borrador_repo)


ListarBorradoresDep = Annotated[ListarBorradores, Depends(get_listar_borradores)]


def get_obtener_borrador(borrador_repo: BorradorRepoDep) -> ObtenerBorrador:
    return ObtenerBorrador(borrador_repo=borrador_repo)


ObtenerBorradorDep = Annotated[ObtenerBorrador, Depends(get_obtener_borrador)]


def get_listar_mis_borradores(
    borrador_repo: BorradorRepoDep,
) -> ListarMisBorradores:
    return ListarMisBorradores(borrador_repo=borrador_repo)


ListarMisBorradoresDep = Annotated[ListarMisBorradores, Depends(get_listar_mis_borradores)]


__all__ = [
    "BorradorRepoDep",
    "GenerarBorradorDep",
    "LLMClientDep",
    "ListarBorradoresDep",
    "ListarMisBorradoresDep",
    "ObtenerBorradorDep",
    "PublicarBorradorDep",
    "ResolvedorPlantillaDep",
]
