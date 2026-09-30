"""Segmentadores genéricos por categoría de fuente.

Las normas, sentencias y libros del corpus tienen segmentador propio por
abreviatura. Las fuentes que suben los usuarios (privadas, luego globales) no: se
segmentan con estos, elegidos por la categoría:

- norma: por artículos («Artículo N»), como el resto de las leyes del corpus.
- jurisprudencia: HECHO (vistos y antecedentes), DERECHO (considerandos) y FALLO
  (por tanto), como las SCP; sin marcadores, se parte por tamaño como derecho.
- doctrina: libro por ventanas con página (reutiliza el segmentador de libros).
"""

from __future__ import annotations

import re

from src.domain.services.segmentacion.base import (
    ArbolJerarquico,
    FragmentoProducible,
    NodoJerarquico,
    SegmentadorNorma,
    enlazar_nodos_jerarquicos,
    partir_bloque_por_tamano,
)
from src.domain.services.segmentacion.doctrina import SegmentadorLibroBase, _segmentar_libro
from src.domain.services.segmentacion.registro import SegmentadorRegistry

RGX_ARTICULO = re.compile(
    r"(?<!\S)Art[ií]culo\s+(\d{1,4})(?:[ºo°]|\s*(?:bis|ter))?\s*[\.\-–:]?", re.I
)
RGX_VISTOS = re.compile(r"(?<!\S)VISTOS\b", re.IGNORECASE)
RGX_CONSIDERANDO = re.compile(r"(?<!\S)CONSIDERANDO\b", re.IGNORECASE)
RGX_POR_TANTO = re.compile(r"(?<!\S)POR TANTO\b", re.IGNORECASE)


class SegmentadorArticulos(SegmentadorNorma):
    """Norma genérica: un fragmento por «Artículo N»."""

    REGEX_ARTICULO = RGX_ARTICULO
    REGEX_ESTRUCTURA = {}

    def __init__(self, abreviatura: str) -> None:
        self.ABREVIATURA = abreviatura
        self.NOMBRE = ""

    def segmentar(self, texto_completo: str) -> ArbolJerarquico:
        abrev = self.ABREVIATURA
        texto = self._strip_basic(texto_completo)
        marcas = list(RGX_ARTICULO.finditer(texto))
        if not marcas:
            raise ValueError(
                f"El texto no tiene artículos reconocibles (Artículo N): {abrev}. "
                "Una norma se segmenta por artículos."
            )
        clave_maestro = f"{abrev}_MASTER"
        nodos = {
            clave_maestro: NodoJerarquico(
                clave=clave_maestro,
                nivel=1,
                titulo=abrev,
                hijos=[],
                metadatos={"tipo_estructura": "MAESTRO_NORMA", "no_indexable": True},
            )
        }
        fragmentos: list[FragmentoProducible] = []
        for i, m in enumerate(marcas):
            fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
            cuerpo = texto[m.start() : fin].strip()
            numero = int(m.group(1))
            fragmentos.append(
                FragmentoProducible(
                    texto=cuerpo,
                    nivel_jerarquico=4,
                    tipo_chunk="articulo_simple",
                    padre_ref_key=f"{abrev}_{numero}_MASTER",
                    metadatos={"numero_articulo": numero},
                )
            )
        return ArbolJerarquico(
            abreviatura=abrev, raices=[clave_maestro], nodos=nodos, fragmentos=fragmentos
        )


class SegmentadorResolucion(SegmentadorNorma):
    """Sentencia o resolución genérica: hecho, derecho y fallo."""

    REGEX_ARTICULO = RGX_CONSIDERANDO
    REGEX_ESTRUCTURA = {}

    def __init__(self, abreviatura: str) -> None:
        self.ABREVIATURA = abreviatura
        self.NOMBRE = ""

    def segmentar(self, texto_completo: str) -> ArbolJerarquico:
        abrev = self.ABREVIATURA
        texto = self._strip_basic(texto_completo)
        m_vis = RGX_VISTOS.search(texto)
        m_con = RGX_CONSIDERANDO.search(texto)
        m_fal = RGX_POR_TANTO.search(texto)

        if m_con and m_fal and m_con.start() < m_fal.start():
            inicio = m_vis.start() if m_vis and m_vis.start() < m_con.start() else 0
            bloques = [
                ("HECHO", inicio, m_con.start(), "fundamento_de_hecho"),
                ("DERECHO", m_con.start(), m_fal.start(), "fundamento_de_derecho_analisis"),
                ("FALLO", m_fal.start(), len(texto), "fundamentacion_del_fallo"),
            ]
        else:
            bloques = [("DERECHO", 0, len(texto), "fundamento_de_derecho_analisis")]

        clave_maestro = f"{abrev}_MASTER"
        nodos = {
            clave_maestro: NodoJerarquico(
                clave=clave_maestro,
                nivel=1,
                titulo=abrev,
                hijos=[],
                metadatos={"tipo_estructura": "MAESTRO_RESOLUCION", "no_indexable": True},
            )
        }
        ocurrencias: list[tuple[int, str, int]] = []
        fragmentos: list[FragmentoProducible] = []
        for nombre_bloque, inicio, fin, tipo_chunk in bloques:
            cuerpo = texto[inicio:fin].strip()
            if not cuerpo:
                continue
            clave_nodo = f"{abrev}_{nombre_bloque}"
            nodos[clave_nodo] = NodoJerarquico(
                clave=clave_nodo,
                nivel=2,
                titulo=nombre_bloque,
                hijos=[],
                metadatos={"tipo_estructura": f"BLOQUE_{nombre_bloque}"},
            )
            ocurrencias.append((inicio, clave_nodo, 2))
            for j, parte in enumerate(partir_bloque_por_tamano(cuerpo)):
                sufijo = "" if j == 0 else f"-p{j + 1}"
                fragmentos.append(
                    FragmentoProducible(
                        texto=parte,
                        nivel_jerarquico=4,
                        tipo_chunk=tipo_chunk,
                        padre_ref_key=f"{clave_nodo}{sufijo}",
                        metadatos={"bloque": nombre_bloque.lower(), "numero_sentencia": abrev},
                    )
                )
        enlazar_nodos_jerarquicos(nodos, ocurrencias)
        return ArbolJerarquico(
            abreviatura=abrev, raices=[clave_maestro], nodos=nodos, fragmentos=fragmentos
        )


class SegmentadorLibroGenerico(SegmentadorLibroBase):
    """Libro sin ficha propia: ventanas con página y master no indexable."""

    def __init__(self, abreviatura: str) -> None:
        self.ABREVIATURA = abreviatura
        self.NOMBRE = ""
        self.FICHA = {"obra": abreviatura}

    def segmentar(self, texto_completo: str) -> ArbolJerarquico:
        return _segmentar_libro(self, texto_completo)


SegmentadorRegistry.registrar_categoria("norma", SegmentadorArticulos)
SegmentadorRegistry.registrar_categoria("jurisprudencia", SegmentadorResolucion)
SegmentadorRegistry.registrar_categoria("doctrina", SegmentadorLibroGenerico)
