"""strip_frontmatter: el frontmatter YAML de las notas del vault no llega al prompt ni a la UI."""

from __future__ import annotations

import pytest

from src.domain.services.criterio_texto import strip_frontmatter


def test_quita_el_bloque_yaml_inicial_y_los_saltos_de_linea_que_siguen() -> None:
    nota = "---\ntitle: Criterio\ntags: [a, b]\n---\n\n\nCuerpo de la nota.\nSegunda linea."

    assert strip_frontmatter(nota) == "Cuerpo de la nota.\nSegunda linea."


def test_el_cierre_consume_exactamente_los_cuatro_caracteres_del_marcador() -> None:
    """Si el cuerpo empieza pegado al cierre no se pierde ninguna letra."""
    assert strip_frontmatter("---\na: 1\n---Cuerpo") == "Cuerpo"


def test_sin_frontmatter_devuelve_el_texto_tal_cual() -> None:
    assert strip_frontmatter("Texto sin metadatos.\n---\nOtra cosa") == (
        "Texto sin metadatos.\n---\nOtra cosa"
    )


def test_frontmatter_sin_cierre_se_deja_intacto() -> None:
    nota = "---\ntitle: sin cerrar\nCuerpo"

    assert strip_frontmatter(nota) == nota


def test_frontmatter_sin_cuerpo_devuelve_vacio() -> None:
    assert strip_frontmatter("---\ntitle: solo metadatos\n---") == ""


def test_solo_quita_el_primer_bloque() -> None:
    nota = "---\na: 1\n---\nCuerpo\n---\nb: 2\n---\nFin"

    assert strip_frontmatter(nota) == "Cuerpo\n---\nb: 2\n---\nFin"


@pytest.mark.parametrize("vacio", ["", "\n"])
def test_texto_vacio(vacio: str) -> None:
    assert strip_frontmatter(vacio) == vacio
