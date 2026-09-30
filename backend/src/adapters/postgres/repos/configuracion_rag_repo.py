"""Repositorio PostgreSQL: ConfiguracionRAGRepo.

Implementa el puerto application.ports.ConfiguracionRAGRepo usando
SQLAlchemy async. La tabla `configuracion_rag` es singleton
(decision D3 del plan): una sola fila activa.

La lectura de runtime usa la sesión async del request para reflejar cambios del
administrador y cerrar explícitamente las transacciones.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.postgres.models.configuracion_rag import ConfiguracionRAGModel
from src.adapters.postgres.repos.config_cache import invalidate_config_cache
from src.application.ports.configuracion_rag_repo import ConfiguracionRAGRepo
from src.domain.entities.configuracion_rag import ConfiguracionRAG


class ConfiguracionRAGRepoImpl(ConfiguracionRAGRepo):
    """Implementacion PostgreSQL de ConfiguracionRAGRepo."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_config(self) -> ConfiguracionRAG:
        """Lee la configuración singleton con la sesión del request.

        El commit explícito cierra la transacción de lectura antes de devolver
        el control a FastAPI y evita conexiones `idle in transaction`.
        """
        result = await self._session.execute(select(ConfiguracionRAGModel).limit(1))
        model = result.scalar_one_or_none()
        await self._session.commit()
        if model is None:
            raise RuntimeError("configuracion_rag vacia")
        return self._to_domain(model)

    @staticmethod
    def _to_domain(model: ConfiguracionRAGModel) -> ConfiguracionRAG:
        return ConfiguracionRAG(
            id=model.id,
            score_threshold=float(model.score_threshold),
            top_k_denso=model.top_k_denso,
            top_k_lexico=model.top_k_lexico,
            top_k_final=model.top_k_final,
            modelo_embeddings=model.modelo_embeddings,
            modelo_llm_default=model.modelo_llm_default,
            actualizado_por=model.actualizado_por,
            updated_at=model.updated_at.isoformat() if model.updated_at else None,
            max_profundidad_bfs=model.max_profundidad_bfs,
            top_k_padres_a_incluir=model.top_k_padres_a_incluir,
            temperatura=model.temperatura,
            reranker_endpoint_id=model.reranker_endpoint_id,
            llm_endpoint_id=model.llm_endpoint_id,
            normalizar_query=model.normalizar_query,
        )

    async def set_llm_endpoint_id(
        self,
        endpoint_id: str | None,
        actualizado_por: int,
    ) -> ConfiguracionRAG:
        """Persiste el endpoint de LLM activo en la fila singleton."""
        stmt = (
            update(ConfiguracionRAGModel)
            .values(
                llm_endpoint_id=endpoint_id,
                actualizado_por=actualizado_por,
                updated_at=datetime.now(UTC),
            )
            .execution_options(synchronize_session="fetch")
        )
        await self._session.execute(stmt)
        await self._session.commit()
        invalidate_config_cache()
        return await self.get_config()

    async def set_reranker_endpoint_id(
        self,
        endpoint_id: str | None,
        actualizado_por: int,
    ) -> ConfiguracionRAG:
        """Persiste reranker_endpoint_id en la fila singleton + actualiza auditoria."""
        stmt = (
            update(ConfiguracionRAGModel)
            .values(
                reranker_endpoint_id=endpoint_id,
                actualizado_por=actualizado_por,
                updated_at=datetime.now(UTC),
            )
            .execution_options(synchronize_session="fetch")
        )
        await self._session.execute(stmt)
        await self._session.commit()
        invalidate_config_cache()
        return await self.get_config()

    async def set_normalizar_query(
        self,
        activado: bool,
        actualizado_por: int,
    ) -> ConfiguracionRAG:
        """Persiste el toggle normalizar_query (Capa A, bug sala)."""
        stmt = (
            update(ConfiguracionRAGModel)
            .values(
                normalizar_query=activado,
                actualizado_por=actualizado_por,
                updated_at=datetime.now(UTC),
            )
            .execution_options(synchronize_session="fetch")
        )
        await self._session.execute(stmt)
        await self._session.commit()
        invalidate_config_cache()
        return await self.get_config()

    async def actualizar(
        self,
        valores: Mapping[str, float | int],
        actualizado_por: int,
    ) -> ConfiguracionRAG:
        """Persiste un ajuste parcial de umbrales en la fila singleton (HU-23).

        `valores` llega ya validado por el dominio
        (validar_parametros_ajustables); la tabla es singleton, igual que
        los setters existentes.
        """
        stmt = (
            update(ConfiguracionRAGModel)
            .values(
                **valores,
                actualizado_por=actualizado_por,
                updated_at=datetime.now(UTC),
            )
            .execution_options(synchronize_session="fetch")
        )
        await self._session.execute(stmt)
        await self._session.commit()
        invalidate_config_cache()
        return await self.get_config()


def get_configuracion_rag_repo(session: AsyncSession) -> ConfiguracionRAGRepo:
    """Factory para inyeccion de dependencias."""
    return ConfiguracionRAGRepoImpl(session)
