"""Entidad de dominio ConfiguracionRAG — singleton con umbrales operativos.

Regla Clean Architecture: dataclass pura, sin SQLAlchemy ni Pydantic.
El ORM vive en adapters/postgres/models/configuracion_rag.py y mapea esta
entidad a la tabla `configuracion_rag` (singleton, D3 del plan).

Estos umbrales son modificables en runtime por el Administrador (HU-23)
sin redeploy, a diferencia de EMBEDDING_DIM (operativa, pre-despliegue).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ConfiguracionRAG:
    """Configuracion singleton del pipeline RAG.

    Atributos:
        id: PK interno. None si no esta persistida (fila singleton).
        score_threshold: Score minimo (0.00-1.00) para aceptar un fragmento
            tras la fusion RRF.
        top_k_denso: Candidatos densos a recuperar en fase 2 (hibrida).
        top_k_lexico: Candidatos lexicos (BM25) a recuperar en fase 2.
        top_k_final: Top K final tras reranking (fase 3).
        modelo_embeddings: Nombre del modelo de embeddings activo.
        modelo_llm_default: Modelo LLM default para Sprint 6.
        actualizado_por: ID del ultimo usuario que la modifico. None si defaults.
        updated_at: Timestamp de la ultima modificacion. None antes de persistir.
        max_profundidad_bfs: Profundidad maxima del CTE recursivo ascendente
            en el ExpansorJerarquico (Sprint 5). Default 3.
        top_k_padres_a_incluir: Limite de nodos padre a inyectar en
            ContextoExpandido (Sprint 5). Default 5.
        temperatura: Temperatura del LLM (Sprint 6). Baja (0.1) para
            rigurosidad legal. Ajustable por admin en runtime.
        reranker_endpoint_id: ID del endpoint de reranker activo (Sprint 3).
            None = usar primer endpoint de RERANKER_ENDPOINTS (default).
            Seleccionable por admin via
            PUT /admin/corpus/configuracion-rag/reranker-endpoint.
        llm_endpoint_id: ID del endpoint de LLM activo (Sprint 6).
            None = usar primer endpoint de LLM_ENDPOINTS (default).
            Seleccionable por admin via
            PUT /admin/corpus/configuracion-rag/llm-endpoint.
        normalizar_query: Activa la limpieza de la query antes del embedding
            (saludos/muletillas/typos — Capa A, bug sala). True por default.
            Desactivable por admin via
            PUT /admin/corpus/configuracion-rag/normalizar-query.
    """

    id: int | None
    score_threshold: float
    top_k_denso: int
    top_k_lexico: int
    top_k_final: int
    modelo_embeddings: str
    modelo_llm_default: str
    # ponytail: añadidos al final para no romper orden posicional existente.
    actualizado_por: int | None = None
    updated_at: str | None = None
    max_profundidad_bfs: int = 3
    top_k_padres_a_incluir: int = 5
    temperatura: float = 0.1
    reranker_endpoint_id: str | None = None
    llm_endpoint_id: str | None = None
    normalizar_query: bool = True


# Umbrales ajustables en runtime por el Administrador (HU-23) con su rango.
# Clave = nombre exacto de la columna en configuracion_rag.
RANGOS_PARAMETROS_AJUSTABLES: dict[str, tuple[float, float]] = {
    "score_threshold": (0.0, 1.0),
    "top_k_denso": (1, 200),
    "top_k_lexico": (1, 200),
    "top_k_final": (1, 100),
    "max_profundidad_bfs": (1, 10),
    "top_k_padres_a_incluir": (0, 50),
    "temperatura": (0.0, 1.5),
}


def validar_parametros_ajustables(
    valores: Mapping[str, Any],
) -> dict[str, float | int]:
    """Filtra y valida campos ajustables de la singleton (HU-23).

    Args:
        valores: {campo: valor} parcial; solo se aceptan claves de
            RANGOS_PARAMETROS_AJUSTABLES dentro de su rango.

    Returns:
        Dict limpio con los campos aceptados (float o int segun rango).

    Raises:
        ValueError: clave desconocida, tipo no numerico (bool incluido)
            o valor fuera de rango.
    """
    limpios: dict[str, float | int] = {}
    for campo, valor in valores.items():
        if campo not in RANGOS_PARAMETROS_AJUSTABLES:
            raise ValueError(f"Parámetro desconocido: '{campo}'.")
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ValueError(f"'{campo}' debe ser numérico.")
        minimo, maximo = RANGOS_PARAMETROS_AJUSTABLES[campo]
        if not (minimo <= valor <= maximo):
            raise ValueError(f"'{campo}' fuera de rango [{minimo}, {maximo}]: {valor}.")
        limpios[campo] = valor
    return limpios
