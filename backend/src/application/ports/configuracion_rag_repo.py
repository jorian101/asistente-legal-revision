"""Port: ConfiguracionRAGRepo — repositorio singleton de umbrales RAG.

Permite al PipelineRAG (Sprint 3) leer umbrales operativos
(score_threshold, top_k_*) desde PostgreSQL en lugar de Settings
(decision D3 del plan: modificable en runtime sin redeploy).

Singleton: la tabla `configuracion_rag` tiene una sola fila activa
(insertada por la migracion 222f48d718c2).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from src.domain.entities.configuracion_rag import ConfiguracionRAG


class ConfiguracionRAGRepo(Protocol):
    """Repositorio de la configuracion singleton del pipeline RAG."""

    async def get_config(self) -> ConfiguracionRAG:
        """Retorna la configuracion singleton activa.

        La fila siempre existe (la migracion la inserta). Si no,
        RuntimeError claro: el sistema esta mal inicializado.
        """
        ...

    async def actualizar(
        self,
        valores: Mapping[str, float | int],
        actualizado_por: int,
    ) -> ConfiguracionRAG:
        """Persiste un ajuste parcial de umbrales en la fila singleton (HU-23).

        Args:
            valores: {campo: valor} ya validado por
                validar_parametros_ajustables (dominio).
            actualizado_por: ID del usuario admin que realiza el cambio.

        Returns:
            ConfiguracionRAG actualizada.
        """
        ...

    async def set_reranker_endpoint_id(
        self,
        endpoint_id: str | None,
        actualizado_por: int,
    ) -> ConfiguracionRAG:
        """Persiste el endpoint de reranker activo en la fila singleton.

        Args:
            endpoint_id: ID del endpoint de RERANKER_ENDPOINTS, o None
                para usar el default (primer endpoint de la lista).
            actualizado_por: ID del usuario admin que realiza el cambio.

        Returns:
            ConfiguracionRAG actualizada.
        """
        ...

    async def set_llm_endpoint_id(
        self,
        endpoint_id: str | None,
        actualizado_por: int,
    ) -> ConfiguracionRAG:
        """Persiste el endpoint de LLM activo en la fila singleton.

        Args:
            endpoint_id: ID del endpoint de LLM_ENDPOINTS, o None
                para usar el default (primer endpoint de la lista).
            actualizado_por: ID del usuario admin que realiza el cambio.

        Returns:
            ConfiguracionRAG actualizada.
        """
        ...

    async def set_normalizar_query(
        self,
        activado: bool,
        actualizado_por: int,
    ) -> ConfiguracionRAG:
        """Persiste el toggle de normalizacion de query (Capa A, bug sala).

        Args:
            activado: True = limpiar saludos/muletillas/typos antes del
                embedding. False = usar la query del usuario tal cual.
            actualizado_por: ID del usuario admin que realiza el cambio.

        Returns:
            ConfiguracionRAG actualizada.
        """
        ...
