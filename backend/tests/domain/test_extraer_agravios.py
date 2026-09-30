"""Tests de ExtraerAgravios (P5) — extracción de agravios del recurso.

Usa el patrón real del auto de vista 04/2026 (caso 3145/3172 Salinas):
"**AGRAVIO N:** <texto>" con 9 agravios agrupados en la resolución.
"""

from __future__ import annotations

import pytest

from src.domain.services.extraer_agravios import (
    AgravioProcesal,
    agravios_a_texto,
    extraer_agravios,
)


class _Frag:
    def __init__(self, texto: str) -> None:
        self.texto = texto
        self.id = 1


def test_extrae_agravios_numerados() -> None:
    """Detecta los patrones '**AGRAVIO N:**' del auto real."""
    texto = (
        "**AGRAVIO 1:** Falta de congruencia por omision del expediente 9999.\n"
        "**AGRAVIO 2:** Erronea aplicacion de la imprescriptibilidad Art. 29 Bis.\n"
        "**AGRAVIO 3:** Resolucion ilegal e infundada."
    )
    agravios = extraer_agravios([_Frag(texto)])
    assert len(agravios) == 3
    assert [a.numero for a in agravios] == [1, 2, 3]
    assert "expediente 9999" in agravios[0].texto
    assert "Art. 29 Bis" in agravios[1].texto


def test_agravios_ordenados_y_dedupe() -> None:
    """Ordena por numero y dedupe repetidos (defensa)."""
    texto = (
        "**AGRAVIO 5:** quinto.\n"
        "**AGRAVIO 2:** segundo.\n"
        "**AGRAVIO 2:** repetido.\n"
        "**AGRAVIO 1:** primero."
    )
    agravios = extraer_agravios([_Frag(texto)])
    assert [a.numero for a in agravios] == [1, 2, 5]


def test_sin_agravios_devuelve_vacio() -> None:
    """Texto sin patron AGRAVIO -> lista vacia."""
    assert extraer_agravios([_Frag("No hay agravios en este fragmento.")]) == []


def test_fragmentos_vacios_devuelve_vacio() -> None:
    """Sin fragmentos -> vacio."""
    assert extraer_agravios([]) == []


def test_agravios_a_texto_formatea() -> None:
    """agravios_a_texto formatea cada agravio numerado para el prompt."""
    texto = agravios_a_texto([AgravioProcesal(numero=1, texto="primero")])
    assert "**AGRAVIO 1:** primero" in texto


def test_agravios_a_texto_vacio() -> None:
    """Sin agravios -> nota de no detectados."""
    assert "No se detectaron agravios" in agravios_a_texto([])


@pytest.mark.parametrize("texto", ["", "   \n\n"])
def test_texto_vacio_o_espacios_devuelve_vacio(texto: str) -> None:
    """Texto vacío o solo espacios -> vacio."""
    assert extraer_agravios([_Frag(texto)]) == []


def test_caso_real_3145_detecta_9_agravios() -> None:
    """P5.4: el auto real Salinas (exp 3145/3172) tiene 9 agravios.

    Lee el documento real del vault (evidencia primaria) y verifica que el
    extractor detecta los 9 agravios con sus textos completos.
    """
    vault = (
        "/home/jorian/proyectos/asistente-legal-vault/sources/casos-tsjm/casos/"
        "exp-3145-3172-apelacion-incidental/documentos/auto_de_vista_04_2026.md"
    )
    import os

    if not os.path.exists(vault):
        pytest.skip("vault no disponible")
    texto = open(vault, encoding="utf-8").read()  # noqa: SIM115

    agravios = extraer_agravios([_Frag(texto)])

    assert [a.numero for a in agravios] == list(range(1, 10)), (
        f"esperaba agravios 1-9, vi {[a.numero for a in agravios]}"
    )
    # Textos reales clave presentes.
    textos = " ".join(a.texto.lower() for a in agravios)
    assert "imprescriptibilidad" in textos  # agravio 2/5 (Art. 29 Bis)
    assert "congruencia" in textos  # agravio 1
    assert "daño económico" in textos or "danio economico" in textos  # 7/8
