"""Migración de las colecciones `jurisprudencia` y `doctrina` (antes solo se creaban al indexar)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from qdrant_migrations.create_fuentes_collections import crear_colecciones


def _cliente(existentes: list[str]) -> MagicMock:
    cliente = MagicMock()
    cliente.get_collections.return_value = SimpleNamespace(
        collections=[SimpleNamespace(name=n) for n in existentes]
    )
    return cliente


def test_crea_las_dos_colecciones_que_faltan():
    cliente = _cliente([])

    creadas = crear_colecciones(cliente, dim=768)

    assert creadas == ["jurisprudencia", "doctrina"]
    nombres = [c.kwargs["collection_name"] for c in cliente.create_collection.call_args_list]
    assert nombres == ["jurisprudencia", "doctrina"]


def test_es_idempotente_si_ya_existen():
    cliente = _cliente(["jurisprudencia", "doctrina"])

    assert crear_colecciones(cliente, dim=768) == []
    cliente.create_collection.assert_not_called()


def test_solo_crea_la_que_falta():
    cliente = _cliente(["jurisprudencia"])

    assert crear_colecciones(cliente, dim=768) == ["doctrina"]
