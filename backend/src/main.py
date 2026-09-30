"""Aplicacion FastAPI — asistente-legal.

Sprint 1 Auth (plan v3, F1.5). Monta routers auth y admin_usuarios.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.adapters.postgres.repos.config_cache import _load_config_cache
from src.application.observability import get_event_bus
from src.application.observability.console_subscriber import (
    iniciar_console_subscriber,
)
from src.routers import (
    admin_consultas,
    admin_formatos,
    admin_metricas,
    admin_permisos,
    admin_usuarios,
    auth,
    borradores,
    chats,
    consultas,
    corpus,
    doctrina,
    expedientes,
    fuentes,
    trabajos,
)

logger = logging.getLogger(__name__)


async def _precalentar_vocabulario() -> None:
    """Carga el vocabulario (SQL de 8-13 s) al arrancar, no en la 1.ª consulta RAG."""
    try:
        from src.adapters.http.dependencies import get_session_factory
        from src.adapters.postgres.vocabulario import get_vocabulario

        async with get_session_factory()() as session:
            await get_vocabulario(session)
    except Exception as exc:  # noqa: BLE001 — best-effort: queda la carga perezosa
        logger.warning("precalentado de vocabulario omitido: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_config_cache()
    # Reconciliación: un reinicio con productores vivos deja consultas en
    # 'en_progreso' eternas; se marcan error (best-effort, no bloquea boot).
    try:
        from src.adapters.http.dependencies import get_session_factory
        from src.adapters.postgres.repos.consulta_historial_repo import (
            get_consulta_historial_repo,
        )

        factory = get_session_factory()
        async with factory() as session:
            n = await get_consulta_historial_repo(session).marcar_error_antiguos()
            if n:
                logger.info("%d consultas en_progreso viejas marcadas como error", n)
    except Exception as exc:  # noqa: BLE001 — nunca bloquear el arranque
        logger.warning("reconciliación omitida: %s", exc)
    vocabulario_task = asyncio.create_task(_precalentar_vocabulario())
    subscriber_task = None
    env = os.environ.get("ENV", os.environ.get("ENVIRONMENT", "development")).lower()
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    if log_level == "DEBUG" or env in ("dev", "development"):
        subscriber_task = asyncio.create_task(iniciar_console_subscriber(get_event_bus()))
    try:
        yield
    finally:
        vocabulario_task.cancel()
        if subscriber_task and not subscriber_task.done():
            subscriber_task.cancel()
        from src.adapters.http.dependencies import cerrar_repos_vectoriales

        cerrar_repos_vectoriales()


app = FastAPI(title="Asistente Legal API", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(admin_usuarios.router)
app.include_router(admin_metricas.router)
app.include_router(admin_consultas.router)
app.include_router(admin_permisos.router)
app.include_router(corpus.router)
app.include_router(doctrina.router)
app.include_router(fuentes.router)
app.include_router(consultas.router)
# Sprint 4 — Gestion de Expedientes + Chats (Opcion B fork #133)
app.include_router(expedientes.router)
app.include_router(chats.router)
# Sprint 6 — Generacion de Respuestas Juridicas
app.include_router(borradores.router)
# Pipeline formatos TSJM (admin)
app.include_router(admin_formatos.router)
app.include_router(trabajos.router)
