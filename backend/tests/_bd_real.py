"""Aislamiento de tests de integracion contra la BD real.

`tests/conftest.py` fija POSTGRES_*=test por defecto y `Settings` es
lru_cache: si otro modulo instancio settings antes con esos defaults
(p.ej. `dependencies*.py` con `_settings` a nivel modulo), un test de
integracion veria la BD `test` en vez de la real con datos sembrados.

`bd_real_asegurada()` re-resuelve Settings con el .env real, falla
rapido si igual ve la BD `test`, y restaura environ + cache al salir
para no contaminar el resto de la suite.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def assert_bd_real(settings: Any) -> None:
    """Falla rapido si settings apunta a la BD `test` de conftest."""
    db = getattr(settings, "postgres_db", "")
    if db == "test":
        raise RuntimeError(
            "test de integracion: POSTGRES_DB=test (cache de Settings con "
            "defaults de conftest). Requiere la BD real con datos sembrados."
        )


@contextmanager
def bd_real_asegurada() -> Generator[Any]:
    """Yieldea Settings resueltos contra la BD real (restaura al salir)."""
    from dotenv import load_dotenv

    from src.config import Settings, get_settings

    env_prev = dict(os.environ)
    load_dotenv(_ENV_PATH, override=True)
    Settings.cache_clear()
    try:
        settings = get_settings()
        assert_bd_real(settings)
        yield settings
    finally:
        os.environ.clear()
        os.environ.update(env_prev)
        Settings.cache_clear()
