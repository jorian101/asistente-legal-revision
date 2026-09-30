"""Tests del helper `particionar_articulo` en segmentacion/base.py.

Cubre 3 ramas de la estrategia:
- Rama numeral: >=2 numerales detectados -> fragmentos tipo_base_numeral.
- Rama parrafo unico: sin numerales, un solo parrafo -> un fragmento tipo_base.
- Rama parrafos multiples: sin numerales, multiples parrafos -> tipo_base_parrafo.
"""

from __future__ import annotations

from src.domain.services.segmentacion.base import particionar_articulo


def test_articulo_con_numerales_genera_uno_por_numeral() -> None:
    """Articulo con 3 numerales (1), (2), (3) -> 3 fragmentos, cada uno tipo_base_numeral.

    Cada numeral debe arrancar en su propia linea para que `_NUMERAL_REGEX`
    (que exige `(?x:^|\\n)` antes del numeral) lo detecte. Sin alineacion de
    linea, el primer numeral se pierde — eso es por diseno de la regex.
    Ver test_primer_numeral_en_misma_que_padre para el caso problematico.
    """
    texto = (
        "(1) Texto del numeral 1: primer parrafo.\n\n"
        "(2) Segundo numeral del articulo.\n\n"
        "(3) Tercer numeral."
    )
    partes = particionar_articulo(
        texto=texto,
        abreviatura="CPPM",
        numero_articulo=42,
        tipo_base="articulo_simple",
        padre_ref_key="CPPM_42_MASTER",
    )

    assert len(partes) == 3, f"esperaba 3 fragmentos, vi {len(partes)}"
    for p in partes:
        assert p.tipo_chunk == "articulo_simple_numeral"
        assert p.nivel_jerarquico == 4
        assert p.padre_ref_key.startswith("CPPM_42_MASTER_")
        assert p.metadatos["numero_articulo"] == 42
        assert p.metadatos["tipo_original"] == "articulo_simple"


def test_articulo_un_parrafo_sin_numerales_devuelve_un_fragm() -> None:
    """Sin numerales y un solo bloque -> 1 fragmento tipo_base (articulo_simple)."""
    texto = "Este es un articulo simple sin subdivisiones, texto corrido."

    partes = particionar_articulo(
        texto=texto,
        abreviatura="LOFA",
        numero_articulo=10,
        tipo_base="articulo_simple",
        padre_ref_key="LOFA_10_MASTER",
    )

    assert len(partes) == 1
    assert partes[0].tipo_chunk == "articulo_simple"
    assert partes[0].padre_ref_key == "LOFA_10_MASTER"


def test_articulo_multiples_parrafos_sin_numerales_particiona() -> None:
    """Sin numerales y \n\n -> tipo_base_parrafo (uno por parrafo)."""
    texto = (
        "Primer parrafo del articulo.\n\n"
        "Segundo parrafo independiente.\n\n"
        "Tercer parrafo, final del articulo."
    )

    partes = particionar_articulo(
        texto=texto,
        abreviatura="LOJM",
        numero_articulo=5,
        tipo_base="articulo_multiparagrafo",
        padre_ref_key="LOJM_5_MASTER",
    )

    assert len(partes) == 3
    for i, p in enumerate(partes):
        assert p.tipo_chunk == "articulo_multiparagrafo_parrafo"
        assert p.nivel_jerarquico == 4
        assert p.padre_ref_key == f"LOJM_5_MASTER_p{i + 1}"


def test_intro_antes_de_numerales_genera_fragmento_maestro() -> None:
    """D-S2C-01: la introducción (tipo penal/sanción) se conserva como maestro.

    La Tabla 18 exige "nodo maestro con la sanción común y numerales que la
    heredan": el primer fragmento lleva la clave padre sin sufijo y los
    numerales la heredan vía padre_ref_key.
    """
    texto = (
        "El que cometiere homicidio será sancionado con 5 a 10 años:\n"
        "(1) Si fuere con alevosía.\n\n"
        "(2) Si fuere por precio.\n\n"
        "(3) En los demás casos."
    )
    partes = particionar_articulo(
        texto=texto,
        abreviatura="CPM",
        numero_articulo=9,
        tipo_base="articulo_simple",
        padre_ref_key="CPM_9_MASTER",
    )

    assert len(partes) == 4
    maestro = partes[0]
    assert "sancionado" in maestro.texto
    assert maestro.padre_ref_key == "CPM_9_MASTER"
    assert maestro.tipo_chunk == "articulo_simple"
    for p in partes[1:]:
        assert p.padre_ref_key.startswith("CPM_9_MASTER_")


def test_numerales_sin_intro_no_generan_maestro() -> None:
    """Sin texto previo al primer numeral no hay fragmento maestro."""
    texto = "(1) Primero.\n\n(2) Segundo."
    partes = particionar_articulo(
        texto=texto,
        abreviatura="CPM",
        numero_articulo=9,
        tipo_base="articulo_simple",
        padre_ref_key="CPM_9_MASTER",
    )

    assert len(partes) == 2


def test_enlazar_nodos_por_posicion() -> None:
    """D-S2C-06 split: hijos se enlazan por posición y nivel."""
    from src.domain.services.segmentacion.base import (
        NodoJerarquico,
        enlazar_nodos_jerarquicos,
    )

    nodos = {
        "X_PARTE_I": NodoJerarquico(
            clave="X_PARTE_I", nivel=1, titulo="PARTE I", hijos=[], metadatos={}
        ),
        "X_TITULO_II": NodoJerarquico(
            clave="X_TITULO_II", nivel=2, titulo="TÍTULO II", hijos=[], metadatos={}
        ),
        "X_CAP_1": NodoJerarquico(
            clave="X_CAP_1", nivel=3, titulo="CAPÍTULO 1", hijos=[], metadatos={}
        ),
    }
    enlazar_nodos_jerarquicos(
        nodos,
        [(0, "X_PARTE_I", 1), (50, "X_TITULO_II", 2), (120, "X_CAP_1", 3)],
    )

    assert nodos["X_PARTE_I"].hijos == ["X_TITULO_II"]
    assert nodos["X_TITULO_II"].hijos == ["X_CAP_1"]
    assert nodos["X_CAP_1"].hijos == []


def test_cpe_enlaza_estructura_en_segmentar() -> None:
    """D-S2C-06 split: SegmentadorCPE deja hijos enlazados."""
    from src.domain.services.segmentacion import cpe  # noqa: F401
    from src.domain.services.segmentacion.registro import SegmentadorRegistry

    arbol = SegmentadorRegistry.obtener("CPE").segmentar(
        "PARTE PRIMERA\nTÍTULO I\nArtículo 1. Texto uno."
    )
    assert arbol.nodos["CPE_PARTE_PRIMERA"].hijos == ["CPE_TITULO_I"]
