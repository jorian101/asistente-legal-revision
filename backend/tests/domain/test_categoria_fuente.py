"""Categoría única de fuente: norma · jurisprudencia · doctrina · obrado.

Norma = ley del corpus; jurisprudencia = sentencias TCP/CIDH y autos de vista
oficializados; doctrina = libros (nunca leyes); obrado = documento del expediente.
"""

from __future__ import annotations

import pytest

from src.domain.services.categoria_fuente import (
    categoria_de_jerarquia,
    categoria_de_obra,
    tipo_fuente_de_obra,
)


@pytest.mark.parametrize(
    "jerarquia,esperada",
    [
        ("suprema", "norma"),
        ("militar", "norma"),
        ("supletoria", "norma"),
        ("jurisprudencia", "jurisprudencia"),
        ("doctrina", "doctrina"),
    ],
)
def test_categoria_de_jerarquia(jerarquia, esperada):
    assert categoria_de_jerarquia(jerarquia) == esperada


@pytest.mark.parametrize(
    "tipo_documento,esperada",
    [
        ("jurisprudencia", "jurisprudencia"),
        ("ejemplo", "jurisprudencia"),  # auto de vista oficializado (N4)
        ("doctrina", "doctrina"),
        ("doctrina_libro", "doctrina"),
        ("material_caso", "doctrina"),
        ("sentencia", "obrado"),
        ("auto_vista", "obrado"),
        ("dictamen_fondo", "obrado"),
        ("otro", "obrado"),
    ],
)
def test_categoria_de_obra(tipo_documento, esperada):
    assert categoria_de_obra(tipo_documento) == esperada


def test_tipo_fuente_de_obra_conserva_obra_para_los_obrados():
    """El payload de Qdrant de los obrados sigue siendo 'obra' (sin migrar)."""
    assert tipo_fuente_de_obra("sentencia") == "obra"
    assert tipo_fuente_de_obra("doctrina") == "doctrina"
    assert tipo_fuente_de_obra("ejemplo") == "jurisprudencia"


def test_jerarquia_desconocida_falla():
    with pytest.raises(ValueError):
        categoria_de_jerarquia("inventada")
