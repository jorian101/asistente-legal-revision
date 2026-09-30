"""Los seeds del vault no deben depender de un id de usuario fijo (26).

En una BD nueva los usuarios de `seed_usuarios.py` tienen otros ids y el seed fallaba con
ForeignKeyViolation en obra.propietario_id. `SEED_PROPIETARIO_ID` permite elegir el dueño;
sin la variable se conserva el 26 historico.
"""

from __future__ import annotations

import importlib

import pytest

SEEDS = [
    ("scripts.seed_doctrina_vault", "_PROPIETARIO"),
    ("scripts.seed_casos_tsjm", "_PROPIETARIO"),
    ("scripts.seed_jurisprudencia_citada", "_PROPIETARIO"),
    ("scripts.seed_criterio_vault", "_PROPIETARIO_DEFAULT"),
]


@pytest.mark.parametrize(("modulo", "nombre"), SEEDS)
def test_el_propietario_se_puede_elegir_por_entorno(monkeypatch, modulo: str, nombre: str) -> None:
    monkeypatch.setenv("SEED_PROPIETARIO_ID", "9")
    mod = importlib.reload(importlib.import_module(modulo))

    assert getattr(mod, nombre) == 9


@pytest.mark.parametrize(("modulo", "nombre"), SEEDS)
def test_sin_variable_se_conserva_el_id_historico(monkeypatch, modulo: str, nombre: str) -> None:
    monkeypatch.delenv("SEED_PROPIETARIO_ID", raising=False)
    mod = importlib.reload(importlib.import_module(modulo))

    assert getattr(mod, nombre) == 26
