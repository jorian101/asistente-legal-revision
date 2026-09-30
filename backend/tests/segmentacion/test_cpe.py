"""Tests del segmentador de la CPE, caracterizados contra el PDF real (411 artículos).

Los textos son SINTÉTICOS. Lo observado en el PDF real: cada Parte repite sus
TÍTULO/CAPÍTULO/SECCIÓN, las Partes se escriben «PRIMERA PARTE» y hay
referencias como «el artículo 339.I de esta Constitución» dentro de frases.
"""

from __future__ import annotations

from src.domain.services.segmentacion.cpe import SegmentadorCPE


def _numeros(arbol) -> list[int]:
    return [f.metadatos["numero_articulo"] for f in arbol.fragmentos]


def test_referencia_dentro_de_una_frase_no_parte_ni_duplica_articulos() -> None:
    texto = (
        "Artículo 339.  \nI. El Presidente decretará.\n"
        "en los casos del artículo 339.I de esta Constitución y el Artículo 234.7 será\n"
        "Artículo 340. Otro artículo.\n"
    )

    arbol = SegmentadorCPE().segmentar(texto)

    assert _numeros(arbol) == [339, 340]
    assert "339.I de esta" in arbol.fragmentos[0].texto  # la referencia queda en su artículo


TEXTO_ESTRUCTURA = """PRIMERA PARTE
TÍTULO I
CAPÍTULO PRIMERO
SECCIÓN I
Artículo 1. Primero.
SEGUNDA PARTE
TÍTULO I
CAPÍTULO PRIMERO
Artículo 2. Segundo, vea el Título IV del presente texto y el Capítulo V.
"""


def test_la_estructura_repetida_en_cada_parte_arma_un_arbol_completo() -> None:
    arbol = SegmentadorCPE().segmentar(TEXTO_ESTRUCTURA)

    assert list(arbol.nodos) == [
        "CPE_PARTE_PRIMERA",
        "CPE_PARTE_SEGUNDA",
        "CPE_TITULO_I",
        "CPE_TITULO_I_2",
        "CPE_CAPITULO_PRIMERO",
        "CPE_CAPITULO_PRIMERO_2",
        "CPE_SECCION_I",
    ]
    assert arbol.raices == ["CPE_PARTE_PRIMERA", "CPE_PARTE_SEGUNDA"]
    assert arbol.nodos["CPE_PARTE_PRIMERA"].hijos == ["CPE_TITULO_I"]
    assert arbol.nodos["CPE_PARTE_SEGUNDA"].hijos == ["CPE_TITULO_I_2"]
    assert arbol.nodos["CPE_TITULO_I_2"].hijos == ["CPE_CAPITULO_PRIMERO_2"]
