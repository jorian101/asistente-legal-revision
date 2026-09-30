"""Tests de SegmentadorCPM (Codigo Penal Militar).

Los textos son SINTETICOS: construidos a partir de los regex del segmentador para
verificar la estructura (libro/titulo/capitulo) y la deteccion de articulos. No
reproducen normas reales.
"""

from __future__ import annotations

import unicodedata

import pytest

from src.domain.services.segmentacion.cpm import SegmentadorCPM

TEXTO = """LIBRO PRIMERO
TITULO I
CAPITULO I
ARTICULO 1°— Este es el primer articulo de prueba sintetico.
ARTÍCULO 2°— Segundo articulo. Contiene texto.
TITULO II
ARTICULO 3°- Tercer articulo sin acento.
"""


def _numeros(arbol) -> list[int]:
    return [f.metadatos["numero_articulo"] for f in arbol.fragmentos]


def test_detecta_libro_titulos_y_capitulos_con_su_jerarquia() -> None:
    arbol = SegmentadorCPM().segmentar(TEXTO)

    assert arbol.abreviatura == "CPM"
    assert arbol.raices == ["CPM_LIBRO_PRIMERO"]
    assert set(arbol.nodos) == {
        "CPM_LIBRO_PRIMERO",
        "CPM_TITULO_I",
        "CPM_TITULO_II",
        "CPM_CAPITULO_I",
    }
    assert arbol.nodos["CPM_LIBRO_PRIMERO"].hijos == ["CPM_TITULO_I", "CPM_TITULO_II"]
    assert arbol.nodos["CPM_TITULO_I"].hijos == ["CPM_CAPITULO_I"]
    assert [
        arbol.nodos[k].nivel for k in ("CPM_LIBRO_PRIMERO", "CPM_TITULO_I", "CPM_CAPITULO_I")
    ] == [
        1,
        2,
        3,
    ]


def test_detecta_los_articulos_con_y_sin_acento_y_con_guion_corto() -> None:
    arbol = SegmentadorCPM().segmentar(TEXTO)

    assert _numeros(arbol) == [1, 2, 3]
    assert [f.padre_ref_key for f in arbol.fragmentos] == [
        "CPM_1_MASTER",
        "CPM_2_MASTER",
        "CPM_3_MASTER",
    ]
    assert all(f.nivel_jerarquico == 4 and f.es_indexable for f in arbol.fragmentos)
    assert arbol.fragmentos[0].texto.startswith("Este es el primer articulo")


@pytest.mark.parametrize(
    "encabezado",
    [
        "ARTICULO 5º— cuerpo",  # ordinal literal
        "ARTICULO. 5°— cuerpo",  # punto tras ARTICULO
        "ARTICULO 5o— cuerpo",  # ordinal normalizado por NFKC
        "ARTICULO 5— cuerpo",  # sin ordinal
    ],
)
def test_variantes_de_encabezado_de_articulo(encabezado: str) -> None:
    arbol = SegmentadorCPM().segmentar(unicodedata.normalize("NFKC", encabezado))

    assert _numeros(arbol) == [5]


def test_articulo_cero_se_ignora() -> None:
    arbol = SegmentadorCPM().segmentar("ARTICULO 0°— nada\nARTICULO 1°— algo")

    assert _numeros(arbol) == [1]


def test_articulo_largo_se_marca_multiparagrafo() -> None:
    cuerpo = "Parrafo de relleno sintetico. " * 40  # > 800 caracteres
    arbol = SegmentadorCPM().segmentar(f"ARTICULO 7°— {cuerpo}")

    assert arbol.fragmentos[0].tipo_chunk != "articulo_simple"


def test_texto_sin_estructura_devuelve_arbol_vacio() -> None:
    arbol = SegmentadorCPM().segmentar("Texto libre sin articulos ni titulos.")

    assert arbol.raices == []
    assert arbol.nodos == {}
    assert arbol.fragmentos == []
