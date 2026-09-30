"""Use case: AjustarParametrosRAG — HU-23 umbrales en runtime.

Permite al Administrador modificar los umbrales operativos del pipeline
RAG (score_threshold, top_k_*, profundidad BFS, temperatura) sin redeploy.
La validacion de whitelist + rangos vive en el dominio
(validar_parametros_ajustables); este UC orquesta y garantiza que no se
envie un ajuste vacio al repo.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from src.domain.entities.configuracion_rag import validar_parametros_ajustables

if TYPE_CHECKING:
    from src.application.ports.configuracion_rag_repo import ConfiguracionRAGRepo


async def ejecutar(
    repo: ConfiguracionRAGRepo,
    valores: Mapping[str, Any],
    actualizado_por: int,
):
    """Valida y persiste un ajuste parcial de la configuracion singleton.

    Args:
        repo: Repositorio de la configuracion singleton.
        valores: {campo: valor} parcial con los parametros a ajustar.
        actualizado_por: ID del admin que realiza el cambio.

    Returns:
        ConfiguracionRAG actualizada.

    Raises:
        ValueError: clave desconocida, tipo invalido, valor fuera de rango
            o dict sin ningun parametro valido.
    """
    limpios = validar_parametros_ajustables(valores)
    if not limpios:
        raise ValueError("No se proporcionó ningún parámetro válido para ajustar.")
    return await repo.actualizar(limpios, actualizado_por=actualizado_por)
