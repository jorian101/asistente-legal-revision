"""Todo modelo del paquete debe quedar registrado al importar `models`.

Alembic autogenera contra `Base.metadata` tras importar solo el paquete: un modelo
que falte alli hace que `alembic revision --autogenerate` proponga DROP TABLE de su
tabla (le paso a `obra_origen` y `recomendacion_doctrina`).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]

_SCRIPT = """
import importlib, pkgutil
import src.adapters.postgres.models as pkg
from src.adapters.postgres.base import Base
registradas = set(Base.metadata.tables)
for m in pkgutil.iter_modules(pkg.__path__):
    importlib.import_module(f"{pkg.__name__}.{m.name}")
print(",".join(sorted(set(Base.metadata.tables) - registradas)))
"""


def test_importar_el_paquete_registra_todas_las_tablas() -> None:
    salida = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        cwd=_BACKEND,
        env={"PYTHONPATH": str(_BACKEND), "PATH": "/usr/bin"},
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout.strip()

    assert salida == "", f"tablas fuera de models/__init__.py: {salida}"
