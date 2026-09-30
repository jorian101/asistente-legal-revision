"""Segmentadores genéricos para fuentes que suben los usuarios (sin segmentador propio)."""

from __future__ import annotations

import pytest

from src.domain.services.segmentacion.registro import SegmentadorRegistry

LEY = """LEY N° 1234
Artículo 1. (Objeto). La presente ley regula el uso de los recursos.

Artículo 2. (Alcance). Se aplica a todas las personas naturales y jurídicas
del territorio nacional.

Artículo 3.- (Definiciones). Para los efectos de esta ley se entiende por recurso
todo bien susceptible de aprovechamiento.
"""

AUTO = """SALA DE APELACIONES Y CONSULTA
VISTOS EN GRADO DE APELACIÓN: El recurso interpuesto contra la Resolución 17/2025.
CONSIDERANDO I: Que, se opuso la excepción.
CONSIDERANDO II: Que, la Sala revisa la competencia según el Art. 180 de la CPE.
POR TANTO: La Sala RESUELVE: CONFIRMAR la Resolución 17/2025.
"""


def test_las_abreviaturas_registradas_siguen_ganando():
    """CPE tiene su segmentador propio: la categoría no lo reemplaza."""
    assert type(SegmentadorRegistry.obtener("CPE", "jurisprudencia")).__name__ == "SegmentadorCPE"


def test_sin_categoria_ni_registro_falla():
    with pytest.raises(KeyError):
        SegmentadorRegistry.obtener("XYZ-1")
    with pytest.raises(KeyError):
        SegmentadorRegistry.obtener("XYZ-1", "inexistente")


def test_norma_generica_segmenta_por_articulos():
    arbol = SegmentadorRegistry.obtener("LEY-1234", "norma").segmentar(LEY)

    numeros = [f.metadatos["numero_articulo"] for f in arbol.fragmentos]
    assert numeros == [1, 2, 3]
    assert {f.tipo_chunk for f in arbol.fragmentos} == {"articulo_simple"}
    assert arbol.fragmentos[0].padre_ref_key == "LEY-1234_1_MASTER"
    assert "recursos" in arbol.fragmentos[0].texto


def test_norma_sin_articulos_falla_con_mensaje_claro():
    with pytest.raises(ValueError, match="art[ií]culos"):
        SegmentadorRegistry.obtener("LEY-9", "norma").segmentar("Texto sin estructura legal.")


def test_jurisprudencia_generica_parte_en_hecho_derecho_y_fallo():
    arbol = SegmentadorRegistry.obtener("JUR-AUTO-1", "jurisprudencia").segmentar(AUTO)

    tipos = [f.tipo_chunk for f in arbol.fragmentos]
    assert tipos == [
        "fundamento_de_hecho",
        "fundamento_de_derecho_analisis",
        "fundamentacion_del_fallo",
    ]
    assert "CONFIRMAR" in arbol.fragmentos[-1].texto
    assert "JUR-AUTO-1_MASTER" in arbol.nodos


def test_jurisprudencia_sin_marcadores_parte_por_tamano():
    arbol = SegmentadorRegistry.obtener("JUR-X", "jurisprudencia").segmentar("Texto. " * 500)

    assert {f.tipo_chunk for f in arbol.fragmentos} == {"fundamento_de_derecho_analisis"}


def test_libro_generico_segmenta_por_ventanas_con_master_no_indexable():
    texto = "\n".join(f"Línea {i} sobre argumentación jurídica y ponderación." for i in range(300))

    arbol = SegmentadorRegistry.obtener("LIB-NUEVO", "doctrina").segmentar(texto)

    assert arbol.fragmentos
    assert {f.tipo_chunk for f in arbol.fragmentos} == {"doctrina_seccion"}
    assert arbol.nodos["LIB-NUEVO_MASTER"].metadatos["no_indexable"] is True
