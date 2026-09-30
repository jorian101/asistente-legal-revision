"""Adapter: SaludSistema — pings de PostgreSQL + Qdrant (HU-22).

Implementa el port application.ports.salud_sistema.SaludSistemaRepo.
Cada check está acotado por timeout y captura excepciones: un componente
caído se reporta con ok=False, nunca derriba el endpoint de salud.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.salud_sistema import (
    SaludInfraestructura,
    SaludSistemaRepo,
)
from src.config import get_settings

log = logging.getLogger(__name__)

_TIMEOUT_PING_S = 5.0


class SaludSistemaImpl(SaludSistemaRepo):
    """Verificación de salud sobre la sesión del request + Qdrant HTTP."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def verificar(self) -> SaludInfraestructura:
        """Ping PostgreSQL (SELECT 1) + Qdrant (get_collection)."""
        postgres_ok = await self._verificar_postgres()
        qdrant_ok, puntos = await self._verificar_qdrant()
        return SaludInfraestructura(
            postgres_ok=postgres_ok,
            qdrant_ok=qdrant_ok,
            qdrant_puntos=puntos,
        )

    async def _verificar_postgres(self) -> bool:
        try:
            await asyncio.wait_for(
                self._session.execute(text("SELECT 1")),
                timeout=_TIMEOUT_PING_S,
            )
            await self._session.commit()
            return True
        except Exception:
            log.warning("Ping PostgreSQL falló", exc_info=True)
            await self._session.rollback()
            return False

    async def _verificar_qdrant(self) -> tuple[bool, int]:
        try:
            return await asyncio.wait_for(self._ping_qdrant(), timeout=_TIMEOUT_PING_S)
        except Exception:
            log.warning("Ping Qdrant falló", exc_info=True)
            return False, 0

    async def _ping_qdrant(self) -> tuple[bool, int]:
        from qdrant_client import QdrantClient

        settings = get_settings()
        client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        try:
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(None, client.get_collection, "corpus_juridico")
            return True, info.points_count or 0
        finally:
            client.close()
