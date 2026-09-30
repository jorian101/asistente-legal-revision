"""Cache en memoria para configuracion_rag (singleton).

Separado para evitar import circular: main.py -> routers -> dependencies -> config_cache
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.adapters.postgres.models.configuracion_rag import ConfiguracionRAGModel
from src.config import get_settings
from src.domain.entities.configuracion_rag import ConfiguracionRAG

_config_cache: ConfiguracionRAG | None = None


def _leer_config(session: Session) -> ConfiguracionRAG:
    model = session.query(ConfiguracionRAGModel).first()
    if model is None:
        raise RuntimeError(
            "Tabla configuracion_rag vacia. La migracion 222f48d718c2 "
            "debe haber insertado la fila singleton. Revisar inicializacion."
        )
    return ConfiguracionRAG(
        id=model.id,
        score_threshold=float(model.score_threshold),
        top_k_denso=model.top_k_denso,
        top_k_lexico=model.top_k_lexico,
        top_k_final=model.top_k_final,
        modelo_embeddings=model.modelo_embeddings,
        modelo_llm_default=model.modelo_llm_default,
        temperatura=model.temperatura,
        actualizado_por=model.actualizado_por,
        updated_at=model.updated_at.isoformat() if model.updated_at else None,
        max_profundidad_bfs=model.max_profundidad_bfs,
        top_k_padres_a_incluir=model.top_k_padres_a_incluir,
        reranker_endpoint_id=model.reranker_endpoint_id,
        llm_endpoint_id=model.llm_endpoint_id,
        normalizar_query=model.normalizar_query,
    )


def _load_config_cache() -> None:
    global _config_cache
    settings = get_settings()
    # connect_timeout: el boot y los tests nunca deben colgarse eternamente
    # si PG no responde (D-S1-14: hilos bloqueados en connect sin timeout).
    engine = create_engine(settings.postgres_url, connect_args={"connect_timeout": 5})
    try:
        with Session(engine) as session:
            _config_cache = _leer_config(session)
    finally:
        engine.dispose()  # sin esto el pool conserva una conexion abierta por carga


def get_cached_config() -> ConfiguracionRAG:
    """Retorna config cacheada (cargada al inicio)."""
    global _config_cache
    if _config_cache is None:
        _load_config_cache()
    return _config_cache


def invalidate_config_cache() -> None:
    """Invalida cache (llamar tras update de reranker_endpoint_id)."""
    global _config_cache
    _config_cache = None
    _load_config_cache()
