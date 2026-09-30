"""La caché de configuración RAG no debe dejar el engine sin liberar.

Cada carga/invalidación crea un engine síncrono; sin `dispose()` su pool
conserva una conexión abierta a PostgreSQL hasta que el GC lo recoja.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.adapters.postgres.repos import config_cache


def test_la_carga_libera_el_engine_incluso_si_falla() -> None:
    engine = MagicMock()
    session = MagicMock()
    session.__enter__.return_value.query.return_value.first.return_value = None  # tabla vacía

    with (
        patch.object(config_cache, "create_engine", return_value=engine),
        patch.object(config_cache, "Session", return_value=session),
        patch.object(config_cache, "get_settings", return_value=MagicMock(postgres_url="x")),
        pytest.raises(RuntimeError),
    ):
        config_cache._load_config_cache()

    engine.dispose.assert_called_once()
