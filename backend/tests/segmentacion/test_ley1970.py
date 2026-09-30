"""Tests de los segmentadores de Ley 1970: Codigo Penal (CP) y Procesal Penal (CPP).

Los textos son SINTETICOS (no reproducen normas reales). El PDF real contiene
ambos codigos; el limite se detecta con el primer articulo 1-10 tras un articulo
>= 350.
"""

from __future__ import annotations

from src.domain.services.segmentacion.ley1970 import (
    SegmentadorLey1970Cp,
    SegmentadorLey1970Cpp,
    _detectar_boundary,
    _extraer_articulos,
)

# CP: arts. 1, 2, 364 (y un 400 fuera de rango) + estructura; luego el CPP reinicia en 1.
TEXTO = """LIBRO PRIMERO
TITULO I
CAPITULO I
Artículo 1. Primer articulo del codigo penal sintetico.
Artículo 2. Segundo del penal.
Artículo 364. Ultimo del penal.
Artículo 400. Numero fuera del rango del CP.
Artículo 1. Primer articulo del procedimiento sintetico.
LIBRO PRIMERO
TITULO I
Artículo 2. Segundo del procedimiento.
Artículo 3. Tercero del procedimiento.
"""


def _numeros(arbol) -> list[int]:
    return [f.metadatos["numero_articulo"] for f in arbol.fragmentos]


def test_extraer_articulos_devuelve_numero_y_posicion() -> None:
    articulos = _extraer_articulos("Artículo 1. a\nartículo 22. b")

    assert [(a.numero, a.inicio) for a in articulos] == [(1, 0), (22, 14)]


def test_boundary_es_el_primer_articulo_1_a_10_tras_uno_de_350_o_mas() -> None:
    articulos = _extraer_articulos(TEXTO)

    assert _detectar_boundary(articulos) == TEXTO.index("Artículo 1. Primer articulo del proced")


def test_boundary_fallback_por_mayor_caida_de_numeracion() -> None:
    texto = "Artículo 1. a\nArtículo 200. b\nArtículo 3. c\n"

    assert _detectar_boundary(_extraer_articulos(texto)) == texto.index("Artículo 3")


def test_boundary_sin_articulos_es_cero() -> None:
    assert _detectar_boundary([]) == 0


def test_cp_toma_solo_los_articulos_anteriores_al_limite_y_hasta_el_364() -> None:
    arbol = SegmentadorLey1970Cp().segmentar(TEXTO)

    assert arbol.abreviatura == "CP"
    assert _numeros(arbol) == [1, 2, 364]  # el 400 se descarta; nada del CPP
    assert [f.padre_ref_key for f in arbol.fragmentos] == [
        "CP_1_MASTER",
        "CP_2_MASTER",
        "CP_364_MASTER",
    ]


def test_cp_arma_libro_titulo_capitulo() -> None:
    arbol = SegmentadorLey1970Cp().segmentar(TEXTO)

    assert arbol.raices == ["CP_LIBRO_PRIMERO"]
    assert arbol.nodos["CP_LIBRO_PRIMERO"].hijos == ["CP_TITULO_I"]
    assert arbol.nodos["CP_TITULO_I"].hijos == ["CP_CAPITULO_I"]
    assert arbol.nodos["CP_CAPITULO_I"].nivel == 3


def test_cpp_toma_los_articulos_desde_el_limite() -> None:
    arbol = SegmentadorLey1970Cpp().segmentar(TEXTO)

    assert arbol.abreviatura == "CPP"
    assert _numeros(arbol) == [1, 2, 3]
    assert [f.padre_ref_key for f in arbol.fragmentos] == [
        "CPP_1_MASTER",
        "CPP_2_MASTER",
        "CPP_3_MASTER",
    ]
    assert arbol.fragmentos[0].texto.startswith("Primer articulo del procedimiento")


def test_cpp_arma_la_estructura_posterior_al_limite_sin_duplicar_hijos() -> None:
    arbol = SegmentadorLey1970Cpp().segmentar(TEXTO)

    assert arbol.raices == ["CPP_LIBRO_PRIMERO"]
    assert arbol.nodos["CPP_LIBRO_PRIMERO"].hijos == ["CPP_TITULO_I"]  # sin duplicados


def test_articulo_largo_se_marca_multiparagrafo() -> None:
    cuerpo = "Parrafo de relleno sintetico. " * 40  # > 800 caracteres
    texto = f"Artículo 364. fin del penal\nArtículo 1. {cuerpo}"

    arbol = SegmentadorLey1970Cpp().segmentar(texto)

    assert arbol.fragmentos[0].tipo_chunk != "articulo_simple"


# ----- F-29 (verificado contra el PDF real consolidado de la Ley 1970) -----


def test_articulo_sin_tilde_en_mayusculas_o_sin_punto_es_articulo() -> None:
    texto = "Articulo 24. (X)\nARTICULO 225. (Y)\nArtículo 140 (Z)\n"

    assert [a.numero for a in _extraer_articulos(texto)] == [24, 225, 140]


def test_referencia_a_un_articulo_dentro_de_una_frase_no_es_articulo() -> None:
    texto = "atenuada conforme al artículo 39. \nArtículo 24. (X)\nvea el artículo 24 de este\n"

    assert [a.numero for a in _extraer_articulos(texto)] == [24]


def test_articulo_tras_salto_de_pagina_sin_salto_de_linea_es_articulo() -> None:
    texto = "autoridad competente. Artículo 139. (Requisitos).\nvea el artículo 24. Otro\n"

    assert [a.numero for a in _extraer_articulos(texto)] == [139]


TEXTO_CPP_REPETIDO = """Artículo 364. Ultimo del penal.
Artículo 1. Primero del procedimiento.
PRIMERA PARTE
LIBRO PRIMERO
TÍTULO I
Artículo 2. Segundo, vea el Capítulo V como Capítulo VI y el Título IV del Código.
SEGUNDA PARTE
LIBRO PRIMERO
TÍTULO I
CAPÍTULO ÚNICO
Artículo 3. Tercero.
"""


def test_estructura_repetida_en_cada_parte_no_pisa_nodos() -> None:
    arbol = SegmentadorLey1970Cpp().segmentar(TEXTO_CPP_REPETIDO)

    assert list(arbol.nodos) == [
        "CPP_LIBRO_PRIMERO",
        "CPP_LIBRO_PRIMERO_2",
        "CPP_TITULO_I",
        "CPP_TITULO_I_2",
        "CPP_CAPITULO_ÚNICO",
    ]
    assert arbol.raices == ["CPP_LIBRO_PRIMERO", "CPP_LIBRO_PRIMERO_2"]
    assert arbol.nodos["CPP_LIBRO_PRIMERO"].hijos == ["CPP_TITULO_I"]
    assert arbol.nodos["CPP_LIBRO_PRIMERO_2"].hijos == ["CPP_TITULO_I_2"]
    assert arbol.nodos["CPP_TITULO_I_2"].hijos == ["CPP_CAPITULO_ÚNICO"]


def test_articulo_con_ordinal_del_cpm_no_es_articulo_de_la_ley_1970() -> None:
    texto = "ARTICULO 22°— (Terminos). Los terminos.\nARTICULO 113°.- Los derechos.\n"

    assert _extraer_articulos(texto) == []


# ----- Artículos Bis/Ter/Quater (43 en el PDF real) -----

TEXTO_BIS = """Artículo 13. Trece.
Artículo 13 Bis. (COMISIÓN POR OMISIÓN). Texto del bis.
Artículo 281 \nBis.-(Racismo) Otro texto.
Artículo 281 ter.(Discriminación) Tercero.
Artículo 321. Bis (TRÁFICO). Trafico.
Artículo 364. Ultimo.
Artículo 1. Procedimiento.
"""


def test_articulos_bis_son_fragmentos_propios_con_sufijo() -> None:
    arbol = SegmentadorLey1970Cp().segmentar(TEXTO_BIS)

    assert [f.padre_ref_key for f in arbol.fragmentos] == [
        "CP_13_MASTER",
        "CP_13_BIS_MASTER",
        "CP_281_BIS_MASTER",
        "CP_281_TER_MASTER",
        "CP_321_BIS_MASTER",
        "CP_364_MASTER",
    ]
    assert [f.metadatos.get("sufijo") for f in arbol.fragmentos] == [
        None,
        "bis",
        "bis",
        "ter",
        "bis",
        None,
    ]
    assert [f.metadatos["numero_articulo"] for f in arbol.fragmentos] == [
        13,
        13,
        281,
        281,
        321,
        364,
    ]
    assert "Texto del bis" not in arbol.fragmentos[0].texto  # ya no se funde con el 13


def test_referencia_a_un_articulo_bis_dentro_de_una_frase_no_es_articulo() -> None:
    texto = "conforme al artículo 185 bis, se dispondrá\nvea. Artículo 20 bis, otro\n"

    assert _extraer_articulos(texto) == []


def test_boundary_ultimo_recurso_devuelve_una_posicion_de_texto() -> None:
    texto = "Artículo 1. a\nArtículo 2. b\nArtículo 3. c\nArtículo 4. d\n"

    assert _detectar_boundary(_extraer_articulos(texto)) == texto.index("Artículo 3")


# ----- Con el texto ya pasado por limpiar_texto_ocr (lo que ve IndexarNorma) -----


def test_un_encabezado_de_articulo_no_se_une_a_la_linea_anterior_sin_punto_final() -> None:
    """La limpieza une las líneas que no acaban en . : ; ? ! y el artículo 81 del PDF real
    sigue a una nota «(Modificado por ...)» sin punto: quedaba pegado y se perdía."""
    from src.domain.services.segmentacion.base import limpiar_texto_ocr

    crudo = (
        "Artículo 80. (X). Texto del ochenta.\n"
        "(Modificado por el artículo 5 de la Ley 054)\n"
        "Artículo 81. (INTERNAMIENTO). Texto del ochenta y uno.\n"
        "Artículo 364. (FINAL). Ultimo.\n"
        "Artículo 1. (PRIMERO). Procedimiento.\n"
    )

    arbol = SegmentadorLey1970Cp().segmentar(limpiar_texto_ocr(crudo))

    assert _numeros(arbol) == [80, 81, 364]


def test_un_encabezado_de_libro_o_titulo_no_se_une_a_la_linea_anterior() -> None:
    from src.domain.services.segmentacion.base import limpiar_texto_ocr

    crudo = (
        "Artículo 364. (FINAL). Ultimo.\n"
        "Artículo 1. (PRIMERO). Procedimiento\n"
        "sin punto final\n"
        "LIBRO PRIMERO\n"
        "TÍTULO I\n"
        "Artículo 2. (SEGUNDO). Otro.\n"
    )

    arbol = SegmentadorLey1970Cpp().segmentar(limpiar_texto_ocr(crudo))

    assert "CPP_LIBRO_PRIMERO" in arbol.nodos
    assert "CPP_TITULO_I" in arbol.nodos


# ----- El cuerpo de un artículo termina en el siguiente encabezado estructural -----

TEXTO_CIERRE = """Artículo 364. (FINAL). Ultimo del penal.
LIBRO SEGUNDO
Artículo 1. (PRIMERO). Texto del uno.
TÍTULO II
EL DELITO
Artículo 2. (SEGUNDO). Texto del dos.
DISPOSICIONES TRANSITORIAS
Primera. Texto ajeno al articulado que no debe pegarse al ultimo articulo.
"""


def _texto(arbol, numero: int) -> str:
    return " ".join(f.texto for f in arbol.fragmentos if f.metadatos["numero_articulo"] == numero)


def test_el_cuerpo_no_arrastra_el_encabezado_estructural_siguiente() -> None:
    arbol = SegmentadorLey1970Cpp().segmentar(TEXTO_CIERRE)

    assert "TÍTULO II" not in _texto(arbol, 1)
    assert "Texto del uno" in _texto(arbol, 1)


def test_el_ultimo_articulo_no_absorbe_las_disposiciones_ni_lo_que_sigue() -> None:
    arbol = SegmentadorLey1970Cpp().segmentar(TEXTO_CIERRE)

    assert "DISPOSICIONES" not in _texto(arbol, 2)
    assert "no debe pegarse" not in _texto(arbol, 2)
    assert "Texto del dos" in _texto(arbol, 2)


def test_el_cp_tampoco_arrastra_el_libro_siguiente() -> None:
    texto = (
        "Artículo 363. (A). Texto.\nLIBRO SEGUNDO\n"
        "Artículo 364. (B). Fin.\nArtículo 1. (X). Proc.\n"
    )

    arbol = SegmentadorLey1970Cp().segmentar(texto)

    assert "LIBRO SEGUNDO" not in _texto(arbol, 363)
