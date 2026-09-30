"""Tests de SegmentadorLOJM (Ley de Organizacion Judicial Militar).

Los textos son SINTETICOS: construidos a partir de los regex del segmentador para
verificar la estructura (titulo/capitulo, sin libro) y la deteccion de articulos.
No reproducen normas reales.
"""

from __future__ import annotations

import unicodedata

import pytest

from src.domain.services.segmentacion.lojm import SegmentadorLOJM

TEXTO = """TITULO PRIMERO
CAPITULO I
ARTICULO 1º.- Primero sintetico.
ARTICULO 2°— Segundo sintetico.
TITULO SEGUNDO
ARTICULO 3.- Tercero sintetico.
"""


def _numeros(arbol) -> list[int]:
    return [f.metadatos["numero_articulo"] for f in arbol.fragmentos]


def test_detecta_titulos_y_capitulos_sin_libro() -> None:
    arbol = SegmentadorLOJM().segmentar(TEXTO)

    assert arbol.abreviatura == "LOJM"
    assert arbol.raices == ["LOJM_TITULO_PRIMERO", "LOJM_TITULO_SEGUNDO"]
    assert set(arbol.nodos) == {
        "LOJM_TITULO_PRIMERO",
        "LOJM_TITULO_SEGUNDO",
        "LOJM_CAPITULO_I",
    }
    assert arbol.nodos["LOJM_TITULO_PRIMERO"].hijos == ["LOJM_CAPITULO_I"]
    assert arbol.nodos["LOJM_TITULO_PRIMERO"].nivel == 2
    assert arbol.nodos["LOJM_CAPITULO_I"].nivel == 3


def test_detecta_articulos_con_distintos_separadores() -> None:
    arbol = SegmentadorLOJM().segmentar(TEXTO)

    assert _numeros(arbol) == [1, 2, 3]
    assert [f.padre_ref_key for f in arbol.fragmentos] == [
        "LOJM_1_MASTER",
        "LOJM_2_MASTER",
        "LOJM_3_MASTER",
    ]
    assert arbol.fragmentos[0].texto.startswith("Primero sintetico")
    assert all(f.nivel_jerarquico == 4 and f.es_indexable for f in arbol.fragmentos)


@pytest.mark.parametrize(
    "encabezado",
    [
        "ARTICULO 9º.- cuerpo",
        "ARTICULO 9° - cuerpo",
        "ARTICULO 9o.- cuerpo",  # ordinal normalizado por NFKC
        "ARTICULO 9— cuerpo",
    ],
)
def test_variantes_de_encabezado_de_articulo(encabezado: str) -> None:
    arbol = SegmentadorLOJM().segmentar(unicodedata.normalize("NFKC", encabezado))

    assert _numeros(arbol) == [9]


def test_articulo_cero_se_ignora() -> None:
    arbol = SegmentadorLOJM().segmentar("ARTICULO 0.- nada\nARTICULO 1.- algo")

    assert _numeros(arbol) == [1]


def test_texto_sin_estructura_devuelve_arbol_vacio() -> None:
    arbol = SegmentadorLOJM().segmentar("Texto libre sin articulos ni titulos.")

    assert arbol.raices == []
    assert arbol.nodos == {}
    assert arbol.fragmentos == []
