"""Tests del repositorio ConfiguracionRAGRepo (PostgreSQL).

Cubre el mapping ORM -> dominio y el manejo de la fila singleton.
La sesion SQLAlchemy se mockea para no requerir DB live.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.postgres.models.configuracion_rag import ConfiguracionRAGModel
from src.adapters.postgres.repos.configuracion_rag_repo import (
    ConfiguracionRAGRepoImpl,
)


def _make_model(**overrides) -> MagicMock:
    """Mock de ConfiguracionRAGModel con valores del Singleton por defecto."""
    m = MagicMock(spec=ConfiguracionRAGModel)
    m.id = overrides.get("id", 1)
    m.score_threshold = overrides.get("score_threshold", 0.75)
    m.top_k_denso = overrides.get("top_k_denso", 40)
    m.top_k_lexico = overrides.get("top_k_lexico", 20)
    m.top_k_final = overrides.get("top_k_final", 7)
    m.modelo_embeddings = overrides.get("modelo_embeddings", "nomic-embed-text")
    m.modelo_llm_default = overrides.get("modelo_llm_default", "llama3:8b")
    m.actualizado_por = overrides.get("actualizado_por")
    m.updated_at = overrides.get("updated_at", datetime(2026, 8, 4))
    m.normalizar_query = overrides.get("normalizar_query", True)
    return m


def _make_session(scalar_one_or_none: object) -> AsyncMock:
    """Mock de AsyncSession donde execute(...).scalar_one_or_none() devuelve el modelo."""
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = scalar_one_or_none
    session.execute.return_value = execute_result
    return session


@pytest.mark.asyncio
async def test_get_config_returns_defaults() -> None:
    """get_config mapea la fila singleton a la entidad con defaults del Singleton."""
    model = _make_model()
    session = _make_session(model)
    repo = ConfiguracionRAGRepoImpl(session)

    cfg = await repo.get_config()

    assert cfg.id == 1
    assert cfg.score_threshold == 0.75
    assert cfg.top_k_denso == 40
    assert cfg.top_k_lexico == 20
    assert cfg.top_k_final == 7
    assert cfg.modelo_embeddings == "nomic-embed-text"
    assert cfg.modelo_llm_default == "llama3:8b"
    assert cfg.actualizado_por is None
    assert cfg.updated_at == "2026-08-04T00:00:00"
    assert cfg.normalizar_query is True  # default (Capa A)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_config_reads_custom_values_from_db() -> None:
    """get_config lee overrides del admin (HU-23: top_k_final custom, etc.)."""
    model = _make_model(
        score_threshold=0.60,
        top_k_denso=60,
        top_k_lexico=30,
        top_k_final=10,
        modelo_embeddings="bge-m3",
        actualizado_por=42,
    )
    session = _make_session(model)
    repo = ConfiguracionRAGRepoImpl(session)

    cfg = await repo.get_config()

    assert cfg.score_threshold == 0.60
    assert cfg.top_k_denso == 60
    assert cfg.top_k_lexico == 30
    assert cfg.top_k_final == 10
    assert cfg.modelo_embeddings == "bge-m3"
    assert cfg.actualizado_por == 42
    assert cfg.normalizar_query is True  # default (Capa A)


@pytest.mark.asyncio
async def test_get_config_raises_when_singleton_missing() -> None:
    """Sin fila singleton -> RuntimeError claro (migracion no aplicada)."""
    session = _make_session(scalar_one_or_none=None)
    repo = ConfiguracionRAGRepoImpl(session)

    with pytest.raises(RuntimeError, match="configuracion_rag vacia"):
        await repo.get_config()


@pytest.mark.asyncio
async def test_set_normalizar_query_persiste_y_commitea(monkeypatch) -> None:
    """Capa A2: set_normalizar_query(False) actualiza y devuelve config actualizada."""
    # Evitar conexion real a BD: la invalidacion de cache recarga con engine sync.
    monkeypatch.setattr(
        "src.adapters.postgres.repos.configuracion_rag_repo.invalidate_config_cache",
        lambda: None,
    )
    model = _make_model(normalizar_query=True)
    session = _make_session(model)
    repo = ConfiguracionRAGRepoImpl(session)

    cfg = await repo.set_normalizar_query(False, actualizado_por=7)

    # Update ejecutado con los valores del toggle.
    update_call = session.execute.await_args
    assert update_call is not None
    # Persistencia: commit llamado.
    session.commit.assert_awaited()
    # Relectura devuelve el modelo (normalizar_query=True en el mock).
    assert cfg.normalizar_query is True


@pytest.mark.asyncio
async def test_actualizar_persiste_valores_y_commitea(monkeypatch) -> None:
    """HU-23: actualizar({campo: valor}) hace UPDATE + commit + relectura."""
    monkeypatch.setattr(
        "src.adapters.postgres.repos.configuracion_rag_repo.invalidate_config_cache",
        lambda: None,
    )
    model = _make_model(top_k_final=10, actualizado_por=7)
    session = _make_session(model)
    repo = ConfiguracionRAGRepoImpl(session)

    cfg = await repo.actualizar({"top_k_final": 10}, actualizado_por=7)

    # 2 executes y 2 commits: UPDATE del ajuste + SELECT/commit de la relectura.
    assert session.execute.await_count == 2
    assert session.commit.await_count == 2
    # Relectura devuelve la entidad mapeada del modelo mockeado.
    assert cfg.top_k_final == 10
    assert cfg.actualizado_por == 7


def test_load_config_cache_usa_connect_timeout(monkeypatch) -> None:
    """D-S1-14: el engine del cache lleva connect_timeout (nunca cuelga eterno)."""
    import src.adapters.postgres.repos.config_cache as config_cache

    llamadas: dict = {}

    def fake_create_engine(url, **kwargs):
        llamadas.update(kwargs)
        raise RuntimeError("sin PG en unit test")

    monkeypatch.setattr(config_cache, "create_engine", fake_create_engine)

    with pytest.raises(RuntimeError, match="sin PG"):
        config_cache._load_config_cache()

    assert llamadas.get("connect_args", {}).get("connect_timeout") == 5
